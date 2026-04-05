from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator, Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Session, SQLModel, create_engine

from .config import settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceDocument(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("source_type", "source_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    source_type: str = Field(index=True)
    source_id: str = Field(index=True)
    title: str
    url: str
    published_at: str | None = None
    normalized_json: str
    raw_json: str
    cached_at: datetime = Field(default_factory=utc_now, index=True)
    expires_at: datetime = Field(index=True)


class QueryCache(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    query_key: str = Field(index=True, unique=True)
    response_json: str
    cached_at: datetime = Field(default_factory=utc_now, index=True)
    expires_at: datetime = Field(index=True)


class EmbeddingCache(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("model", "content_hash"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    model: str = Field(index=True)
    content_hash: str = Field(index=True)
    embedding_json: str
    created_at: datetime = Field(default_factory=utc_now, index=True)


class RequestTrace(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    request_id: str = Field(index=True, unique=True)
    route: str = Field(index=True)
    cached: bool = False
    degraded: bool = False
    source_ids_json: str
    timings_json: str
    created_at: datetime = Field(default_factory=utc_now, index=True)


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

