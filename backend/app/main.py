from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from .config import settings
from .database import get_session, init_db
from .schemas import HealthResponse, NormalizedSource, QARequest, QAResponse, SourceDetailResponse
from .services.cache import cleanup_expired, get_source_document_row
from .services.clinicaltrials import ClinicalTrialsService
from .services.llm_service import LLMService
from .services.pubmed import PubMedService
from .services.qa import QAService
from .services.rerank import HybridReranker


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.last_cache_cleanup_at = None
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_service() -> QAService:
    llm_service = LLMService()
    return QAService(
        llm_service=llm_service,
        clinical_trials_service=ClinicalTrialsService(),
        pubmed_service=PubMedService(),
        reranker=HybridReranker(llm_service),
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Clinical QA MVP backend is running."}


@app.post(f"{settings.api_prefix}/qa", response_model=QAResponse)
async def answer_question(
    payload: QARequest,
    session: Session = Depends(get_session),
) -> QAResponse:
    service = build_service()
    try:
        response = await service.answer(session, payload)
        app.state.last_cache_cleanup_at = response.debug.get("cache_cleanup_at")
        return response
    finally:
        await service.llm_service.aclose()


@app.get(f"{settings.api_prefix}/sources/{{source_type}}/{{source_id}}", response_model=SourceDetailResponse)
async def get_source_detail(
    source_type: str,
    source_id: str,
    session: Session = Depends(get_session),
) -> SourceDetailResponse:
    row = get_source_document_row(session, source_type, source_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Source not found in local cache")
    normalized = NormalizedSource.model_validate_json(row.normalized_json)
    source = SourceDetailResponse(
        source_type=normalized.source_type,
        source_id=normalized.source_id,
        identifier=normalized.identifier,
        title=normalized.title,
        url=normalized.url,
        published_at=normalized.published_at,
        metadata=normalized.metadata,
        snippets=normalized.snippets,
        cached_at=row.cached_at.isoformat(),
    )
    return source


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse)
async def health(
    session: Session = Depends(get_session),
) -> HealthResponse:
    cleanup_at = cleanup_expired(session)
    app.state.last_cache_cleanup_at = cleanup_at
    llm_service = LLMService()
    try:
        return HealthResponse(
            status="ok",
            sqlite_ok=True,
            chat_provider=llm_service.chat_provider_name,
            embedding_provider=llm_service.embedding_provider_name,
            chat_configured=llm_service.chat_configured,
            embedding_configured=llm_service.embedding_configured,
            last_cache_cleanup_at=cleanup_at,
        )
    finally:
        await llm_service.aclose()
