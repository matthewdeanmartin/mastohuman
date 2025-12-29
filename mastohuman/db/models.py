from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    server_account_id: str  # Numeric ID from server, stored as string
    acct: str = Field(unique=True, index=True)  # Canonical: user@instance
    display_name: Optional[str] = None
    url: Optional[str] = None
    avatar_url: Optional[str] = None
    bot: Optional[bool] = False
    created_at: Optional[datetime] = None
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_fetch_at: Optional[datetime] = None


class Status(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    remote_id: str = Field(unique=True, index=True)  # Unique ID from server
    account_acct: str = Field(index=True, foreign_key="account.acct")
    created_at: datetime = Field(index=True)
    uri: Optional[str] = None
    url: Optional[str] = None
    content_html: str
    content_text: str
    language: Optional[str] = None
    visibility: Optional[str] = None
    is_boost: bool = False
    is_reply: bool = False
    in_reply_to_id: Optional[str] = None
    reblog_remote_id: Optional[str] = None
    conversation_id: Optional[str] = None
    media_attachments_json: Optional[str] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class IngestRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    since_hours: int
    notes: Optional[str] = None


class PersonDoc(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_acct: str = Field(unique=True)
    doc_hash: str
    doc_text: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class Summary(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_acct: str = Field(unique=True)
    doc_hash: str
    headline: str
    blurb: str
    tags_json: Optional[str] = None
    llm_provider: str
    llm_model: str
    prompt_version: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
