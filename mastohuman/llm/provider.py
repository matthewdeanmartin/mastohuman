import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel
from sqlmodel import Session, select

from mastohuman.config.settings import settings
from mastohuman.db.models import Account, PersonDoc, Status, Summary
from mastohuman.etl.normalize import create_person_document_text

logger = logging.getLogger(__name__)


class SummaryOutput(BaseModel):
    headline: str
    blurb: str
    tags: List[str] = []


class LLMProvider(ABC):
    @abstractmethod
    def generate_summary(self, text: str) -> SummaryOutput:
        pass


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.client = OpenAI(
            api_key=(
                settings.llm_api_key.get_secret_value()
                if settings.llm_api_key
                else None
            ),
            base_url=str(settings.llm_base_url) if settings.llm_base_url else None,
        )
        self.model = settings.llm_model

    def generate_summary(self, text: str) -> SummaryOutput:
        prompt = (
            "You are a helpful personal news editor. "
            "Analyze the following social media posts from a specific person. "
            "Write a concise, engaging news headline (max 80 chars) and a short summary blurb (1-3 sentences) "
            "describing what they have been posting about recently. "
            "Focus on the most recent content. "
            "Return JSON matching: {headline, blurb, tags}."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text},
                ],
                temperature=settings.llm_temperature,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            return SummaryOutput(**data)
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            # Fallback
            return SummaryOutput(
                headline="Summary Unavailable", blurb="Could not generate summary."
            )


class Summarizer:
    def __init__(self, session: Session):
        self.db = session
        if settings.llm_provider == "openai" or settings.llm_provider == "openrouter":
            self.provider = OpenAIProvider()
        else:
            self.provider = None  # Handle "none" or other providers

    def process_all(self, force: bool = False, limit: Optional[int] = None):
        """
        Generates summaries for accounts seen in the last run.
        """
        # Get accounts seen in last 24h
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        stmt = select(Account).where(Account.last_seen_at >= cutoff)

        # FIX: Prioritize accounts that were just fetched (newest last_fetch_at)
        # This aligns the Summarizer with the Ingest step during limited runs.
        stmt = (
            select(Account)
            .where(Account.last_seen_at >= cutoff)
            .order_by(Account.last_fetch_at.desc())
        )

        if limit:
            stmt = stmt.limit(limit)

        accounts = self.db.exec(stmt).all()
        logger.info(
            f"Processing summaries for {len(accounts)} accounts (Limit: {limit})"
        )

        for account in accounts:
            self._process_account(account, force)

    def _process_account(self, account: Account, force: bool):
        # 1. Fetch original posts from DB
        stmt = (
            select(Status)
            .where(
                Status.account_acct == account.acct,
                Status.is_reply == False,
                Status.is_boost == False,
            )
            .order_by(Status.created_at.desc())
            .limit(settings.max_profile_statuses)
        )

        statuses = self.db.exec(stmt).all()

        if not statuses:
            logger.info(f"No original statuses for {account.acct}, skipping summary.")
            return

        # 2. Build Person Document
        # Convert SQLModel objects to dicts for the helper
        status_dicts = [
            {"created_at": s.created_at, "content_text": s.content_text}
            for s in statuses
        ]
        account_dict = {"display_name": account.display_name, "acct": account.acct}

        doc_text = f"Stats: {len(statuses)} posts\n"  # simple salt

        doc_text = create_person_document_text(account_dict, status_dicts)

        doc_hash = hashlib.sha256(doc_text.encode("utf-8")).hexdigest()

        # 3. Check Cache
        existing_sum = self.db.exec(
            select(Summary).where(
                Summary.account_acct == account.acct, Summary.doc_hash == doc_hash
            )
        ).first()

        if existing_sum and not force:
            logger.debug(f"Summary cached for {account.acct}")
            return

        # 4. Generate
        if not self.provider:
            logger.warning("No LLM provider configured.")
            return

        logger.info(f"Summarizing {account.acct}...")
        result = self.provider.generate_summary(doc_text)

        # 5. Save
        # Upsert logic: delete old summary for this user? Or keep history?
        # Spec implies one valid summary per user for the site, but table has history.
        # We will delete the old one to keep the table clean or just insert a new one.
        # Let's delete old for this user to ensure simple querying.
        existing = self.db.exec(
            select(Summary).where(Summary.account_acct == account.acct)
        ).first()
        if existing:
            self.db.delete(existing)

        new_summary = Summary(
            account_acct=account.acct,
            doc_hash=doc_hash,
            headline=result.headline,
            blurb=result.blurb,
            tags_json=json.dumps(result.tags),
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            prompt_version="1.0",
        )
        self.db.add(new_summary)

        # Also save the PersonDoc for debugging
        # Delete old doc?
        old_doc = self.db.exec(
            select(PersonDoc).where(PersonDoc.account_acct == account.acct)
        ).first()
        if old_doc:
            self.db.delete(old_doc)

        new_doc = PersonDoc(
            account_acct=account.acct, doc_hash=doc_hash, doc_text=doc_text
        )
        self.db.add(new_doc)

        self.db.commit()
