import logging
from datetime import datetime, timedelta, timezone
from typing import List, Set

from sqlmodel import Session, select

from mastohuman.config.settings import settings
from mastohuman.db.models import Account, IngestRun, Status
from mastohuman.etl.normalize import normalize_content
from mastohuman.mastodon_client.client import MastodonClient

logger = logging.getLogger(__name__)


class IngestionManager:
    def __init__(self, session: Session):
        self.db = session
        self.client = MastodonClient()

    def run_pipeline(self, since_hours: int = 24, force_fetch: bool = False):
        """
        Main entry point for 'ingest' command.
        Strategy:
        1. Identify who we follow (Source of Truth).
        2. Update local Account registry.
        3. Sync statuses for all accounts.
        """
        run_start = datetime.now(timezone.utc)

        # 1. User Discovery (Sync Following)
        followed_accounts = self._sync_following_list()
        logger.info(f"Registry updated. Monitoring {len(followed_accounts)} accounts.")

        # 2. Backfill / Sync Content
        # We iterate over everyone we follow.
        # Note: _sync_author has internal logic (overlap/age limits) to keep this fast
        # for frequent runners.
        for acct in followed_accounts:
            self._sync_author(acct, force_fetch)

        # Record Run
        run_record = IngestRun(
            started_at=run_start,
            completed_at=datetime.now(timezone.utc),
            since_hours=since_hours,
        )
        self.db.add(run_record)
        self.db.commit()
        logger.info("Ingestion complete.")

    def _sync_following_list(self) -> List[str]:
        """
        Fetches the complete list of accounts the user follows.
        Upserts them into the DB and returns a list of 'acct' strings.
        """
        logger.info("Fetching 'Following' list...")

        # 1. Get My ID
        me = self.client.get_me()
        my_id = me["id"]

        known_accts = []

        # 2. Paginate through following
        for page in self.client.paginate(
            self.client.get_account_following, account_id=my_id, limit=80
        ):
            for api_account in page:
                self._upsert_account(api_account)
                known_accts.append(api_account["acct"])

        return known_accts

    def _upsert_account(self, api_account: dict):
        """Ensures account exists in DB and updates metadata."""
        acct = api_account["acct"]
        stmt = select(Account).where(Account.acct == acct)
        existing = self.db.exec(stmt).first()

        # Mastodon.py returns datetime objects for 'created_at'
        if not existing:
            existing = Account(
                server_account_id=str(api_account["id"]),
                acct=acct,
                created_at=api_account["created_at"],
            )

        # Update mutable fields
        existing.display_name = api_account.get("display_name")
        existing.url = api_account.get("url")
        existing.avatar_url = api_account.get("avatar")
        existing.bot = api_account.get("bot")
        # We update last_seen_at here to confirm they are still in our follow list
        existing.last_seen_at = datetime.now(timezone.utc)

        self.db.add(existing)
        self.db.commit()

    def _sync_author(self, acct: str, force_fetch: bool):
        """
        Fetches history for a specific author.
        """
        stmt = select(Account).where(Account.acct == acct)
        account = self.db.exec(stmt).first()
        if not account:
            return

        # Optimization: Skip if we fetched very recently (e.g., within 15 mins)
        # to prevent hammering API on repeated runs.
        if not force_fetch and account.last_fetch_at:
            delta = datetime.now(timezone.utc) - account.last_fetch_at.replace(
                tzinfo=timezone.utc
            )
            if delta < timedelta(minutes=15):
                logger.debug(f"Skipping {acct} (synced {int(delta.seconds / 60)}m ago)")
                return

        logger.info(f"Syncing author: {acct}...")

        fetched_count = 0
        cutoff_date = datetime.now(timezone.utc) - timedelta(
            days=settings.max_profile_age_days
        )

        # Iterate pages
        for page in self.client.paginate(
            self.client.get_account_statuses,
            account_id=account.server_account_id,
            limit=40,
        ):
            page_existing_count = 0
            page_items_count = len(page)

            for post in page:
                created_at = post["created_at"]

                # 1. Date Cutoff
                if created_at < cutoff_date:
                    logger.debug(f"Reached age limit for {acct}.")
                    self._mark_account_synced(account)
                    return

                # 2. Exclude Boosts
                if post.get("reblog"):
                    continue

                # Check existence
                remote_id = str(post["id"])
                existing_stmt = select(Status).where(Status.remote_id == remote_id)
                if self.db.exec(existing_stmt).first():
                    page_existing_count += 1
                    continue

                # Insert new Status
                is_reply = post["in_reply_to_id"] is not None

                new_status = Status(
                    remote_id=remote_id,
                    account_acct=acct,
                    created_at=created_at,
                    content_html=post.get("content", ""),
                    content_text=normalize_content(post.get("content", "")),
                    url=post.get("url"),
                    is_reply=is_reply,
                    in_reply_to_id=str(post["in_reply_to_id"]) if is_reply else None,
                    visibility=post.get("visibility"),
                )
                self.db.add(new_status)
                fetched_count += 1

            self.db.commit()

            # Overlap Stop Rule
            if (
                not force_fetch
                and page_items_count > 0
                and page_existing_count == page_items_count
            ):
                logger.debug(f"Overlap detected for {acct}. Stopping sync.")
                break

            # Max Count Rule
            if fetched_count >= settings.max_profile_statuses:
                break

        self._mark_account_synced(account)

    def _mark_account_synced(self, account: Account):
        account.last_fetch_at = datetime.now(timezone.utc)
        self.db.add(account)
        self.db.commit()
