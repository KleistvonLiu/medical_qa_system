from __future__ import annotations

import hashlib
from datetime import timedelta, timezone

import orjson
from sqlmodel import Session, select

from ..database import EmbeddingCache, QueryCache, RequestTrace, SourceDocument, utc_now
from ..schemas import NormalizedSource, QAResponse
from .text_utils import normalize_question


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_query_cache_key(
    question: str,
    filters: dict,
    max_sources: int,
    runtime_context: dict | None = None,
) -> str:
    payload = orjson.dumps(
        {
            "question": normalize_question(question),
            "filters": filters,
            "max_sources": max_sources,
            "runtime_context": runtime_context or {},
        },
        option=orjson.OPT_SORT_KEYS,
    )
    return hashlib.sha256(payload).hexdigest()


def cleanup_expired(session: Session) -> str:
    now = utc_now()
    for row in session.exec(select(QueryCache).where(QueryCache.expires_at < now)).all():
        session.delete(row)
    for row in session.exec(select(SourceDocument).where(SourceDocument.expires_at < now)).all():
        session.delete(row)
    session.commit()
    return now.isoformat()


def get_cached_response(session: Session, query_key: str) -> QAResponse | None:
    now = utc_now()
    row = session.exec(select(QueryCache).where(QueryCache.query_key == query_key)).first()
    if row is None:
        return None
    if _as_utc(row.expires_at) < now:
        session.delete(row)
        session.commit()
        return None
    return QAResponse.model_validate_json(row.response_json)


def set_cached_response(
    session: Session,
    query_key: str,
    response: QAResponse,
    ttl_hours: int,
) -> None:
    now = utc_now()
    row = session.exec(select(QueryCache).where(QueryCache.query_key == query_key)).first()
    payload = response.model_dump_json()
    if row is None:
        row = QueryCache(
            query_key=query_key,
            response_json=payload,
            cached_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        session.add(row)
    else:
        row.response_json = payload
        row.cached_at = now
        row.expires_at = now + timedelta(hours=ttl_hours)
    session.commit()


def get_source_document_row(
    session: Session,
    source_type: str,
    source_id: str,
) -> SourceDocument | None:
    now = utc_now()
    row = session.exec(
        select(SourceDocument).where(
            SourceDocument.source_type == source_type,
            SourceDocument.source_id == source_id,
        )
    ).first()
    if row is None:
        return None
    if _as_utc(row.expires_at) < now:
        session.delete(row)
        session.commit()
        return None
    return row


def get_source_document(
    session: Session,
    source_type: str,
    source_id: str,
) -> NormalizedSource | None:
    row = get_source_document_row(session, source_type, source_id)
    if row is None:
        return None
    return NormalizedSource.model_validate_json(row.normalized_json)


def upsert_source_document(
    session: Session,
    source: NormalizedSource,
    ttl_hours: int,
) -> None:
    now = utc_now()
    row = get_source_document_row(session, source.source_type.value, source.source_id)
    normalized_json = source.model_dump_json()
    raw_json = orjson.dumps(source.raw_payload).decode("utf-8")
    if row is None:
        row = SourceDocument(
            source_type=source.source_type.value,
            source_id=source.source_id,
            title=source.title,
            url=source.url,
            published_at=source.published_at,
            normalized_json=normalized_json,
            raw_json=raw_json,
            cached_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        session.add(row)
    else:
        row.title = source.title
        row.url = source.url
        row.published_at = source.published_at
        row.normalized_json = normalized_json
        row.raw_json = raw_json
        row.cached_at = now
        row.expires_at = now + timedelta(hours=ttl_hours)
    session.commit()


def get_embedding(session: Session, model: str, content_hash: str) -> list[float] | None:
    row = session.exec(
        select(EmbeddingCache).where(
            EmbeddingCache.model == model,
            EmbeddingCache.content_hash == content_hash,
        )
    ).first()
    if row is None:
        return None
    return orjson.loads(row.embedding_json)


def set_embedding(
    session: Session,
    model: str,
    content_hash: str,
    embedding: list[float],
) -> None:
    row = session.exec(
        select(EmbeddingCache).where(
            EmbeddingCache.model == model,
            EmbeddingCache.content_hash == content_hash,
        )
    ).first()
    payload = orjson.dumps(embedding).decode("utf-8")
    if row is None:
        row = EmbeddingCache(
            model=model,
            content_hash=content_hash,
            embedding_json=payload,
        )
        session.add(row)
    else:
        row.embedding_json = payload
    session.commit()


def record_request_trace(
    session: Session,
    request_id: str,
    route: str,
    cached: bool,
    degraded: bool,
    source_ids: list[str],
    timings: dict,
) -> None:
    row = RequestTrace(
        request_id=request_id,
        route=route,
        cached=cached,
        degraded=degraded,
        source_ids_json=orjson.dumps(source_ids).decode("utf-8"),
        timings_json=orjson.dumps(timings).decode("utf-8"),
    )
    session.add(row)
    session.commit()
