from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    clinical_trials = "clinical_trials"
    pubmed = "pubmed"


class RetrievalRoute(str, Enum):
    trials = "trials"
    pubmed = "pubmed"
    blended = "blended"


class QAFilters(BaseModel):
    recruiting_only: bool = False
    recent_literature_only: bool = False


class QARequest(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    filters: QAFilters = Field(default_factory=QAFilters)
    max_sources: int = Field(default=6, ge=1, le=8)


class QuestionIntent(BaseModel):
    route: RetrievalRoute
    focus: str
    condition_terms: list[str] = Field(default_factory=list)
    intervention_terms: list[str] = Field(default_factory=list)
    population_terms: list[str] = Field(default_factory=list)
    outcome_terms: list[str] = Field(default_factory=list)
    filters: QAFilters = Field(default_factory=QAFilters)


class EvidenceSnippet(BaseModel):
    snippet_id: str
    source_type: SourceType
    source_id: str
    identifier: str
    title: str
    section: str
    text: str
    score: float = 0.0
    source_rank: int = 99
    url: str
    published_at: str | None = None


class NormalizedSource(BaseModel):
    source_type: SourceType
    source_id: str
    identifier: str
    title: str
    url: str
    published_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    snippets: list[EvidenceSnippet] = Field(default_factory=list)


class Citation(BaseModel):
    snippet_id: str
    source_type: SourceType
    source_id: str
    identifier: str
    title: str
    section: str
    text: str
    url: str
    published_at: str | None = None
    score: float = 0.0


class QAAnswerDraft(BaseModel):
    direct_answer: str
    why_this_answer: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)


class TraceCard(BaseModel):
    title: str
    body: str


class TraceStage(BaseModel):
    stage_id: str
    title: str
    status: str
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    cards: list[TraceCard] = Field(default_factory=list)
    raw_json: dict[str, Any] = Field(default_factory=dict)


class TraceSummary(BaseModel):
    degraded: bool
    degraded_reason: str | None = None
    cache_hit: bool = False
    route: RetrievalRoute
    total_ms: float = 0.0


class PipelineTrace(BaseModel):
    enabled: bool = True
    language: str = "en"
    summary: TraceSummary
    stages: list[TraceStage] = Field(default_factory=list)


class QAResponse(BaseModel):
    request_id: str
    direct_answer: str
    why_this_answer: list[str]
    limitations: list[str]
    citations: list[Citation]
    source_groups: dict[str, list[Citation]]
    route: RetrievalRoute
    cached: bool
    degraded: bool
    trace: PipelineTrace
    debug: dict[str, Any] = Field(default_factory=dict)


class SourceDetailResponse(BaseModel):
    source_type: SourceType
    source_id: str
    identifier: str
    title: str
    url: str
    published_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    snippets: list[EvidenceSnippet] = Field(default_factory=list)
    cached_at: str


class HealthResponse(BaseModel):
    status: str
    sqlite_ok: bool
    chat_provider: str
    embedding_provider: str
    chat_configured: bool
    embedding_configured: bool
    last_cache_cleanup_at: str | None = None
