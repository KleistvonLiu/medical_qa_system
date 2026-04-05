from __future__ import annotations

from typing import Any, Iterable, Sequence

from ..schemas import (
    Citation,
    EvidenceSnippet,
    NormalizedSource,
    PipelineTrace,
    QAAnswerDraft,
    RetrievalRoute,
    TraceCard,
    TraceStage,
    TraceSummary,
)


STAGE_ORDER = [
    "cache",
    "intent",
    "clinical_trials_retrieval",
    "pubmed_retrieval",
    "rerank",
    "answer_generation",
    "citation_validation",
    "final_response",
]

STAGE_TITLES = {
    "cache": "Cache lookup",
    "intent": "Intent analysis",
    "clinical_trials_retrieval": "ClinicalTrials.gov retrieval",
    "pubmed_retrieval": "PubMed retrieval",
    "rerank": "Snippet reranking",
    "answer_generation": "Answer generation",
    "citation_validation": "Citation validation",
    "final_response": "Final response assembly",
}

SECRET_KEYS = {"api_key", "authorization", "auth", "headers"}


def build_pipeline_trace(
    *,
    route: RetrievalRoute,
    stages: list[TraceStage],
    degraded: bool,
    degraded_reason: str | None,
    cache_hit: bool,
    total_ms: float,
) -> PipelineTrace:
    stage_lookup = {stage.stage_id: stage for stage in stages}
    ordered = [
        stage_lookup.get(stage_id)
        or TraceStage(
            stage_id=stage_id,
            title=STAGE_TITLES[stage_id],
            status="skipped",
            summary="This stage was not executed for the current request.",
        )
        for stage_id in STAGE_ORDER
    ]
    return PipelineTrace(
        enabled=True,
        language="en",
        summary=TraceSummary(
            degraded=degraded,
            degraded_reason=degraded_reason,
            cache_hit=cache_hit,
            route=route,
            total_ms=round(total_ms, 2),
        ),
        stages=ordered,
    )


def make_stage(
    stage_id: str,
    *,
    status: str,
    summary: str,
    metrics: dict[str, Any] | None = None,
    cards: list[TraceCard] | None = None,
    raw_json: dict[str, Any] | None = None,
) -> TraceStage:
    return TraceStage(
        stage_id=stage_id,
        title=STAGE_TITLES[stage_id],
        status=status,
        summary=summary,
        metrics=metrics or {},
        cards=cards or [],
        raw_json=sanitize_trace_value(raw_json or {}),
    )


def card(title: str, body: str) -> TraceCard:
    return TraceCard(title=title, body=_truncate_string(body))


def source_preview(source: NormalizedSource) -> dict[str, Any]:
    return sanitize_trace_value(
        {
            "source_id": source.source_id,
            "identifier": source.identifier,
            "title": source.title,
            "published_at": source.published_at,
            "metadata": source.metadata,
            "snippet_count": len(source.snippets),
            "snippets": [snippet_preview(snippet) for snippet in source.snippets[:4]],
        }
    )


def snippet_preview(snippet: EvidenceSnippet, include_score: bool = True) -> dict[str, Any]:
    preview = {
        "snippet_id": snippet.snippet_id,
        "identifier": snippet.identifier,
        "title": snippet.title,
        "section": snippet.section,
        "text": snippet.text,
        "source_rank": snippet.source_rank,
    }
    if include_score:
        preview["score"] = snippet.score
    return sanitize_trace_value(preview)


def answer_preview(draft: QAAnswerDraft) -> dict[str, Any]:
    return sanitize_trace_value(draft.model_dump())


def citations_preview(citations: Sequence[Citation]) -> list[dict[str, Any]]:
    return [sanitize_trace_value(citation.model_dump()) for citation in citations]


def sanitize_trace_value(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return _truncate_string(str(value))
    if isinstance(value, str):
        return _truncate_string(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in SECRET_KEYS:
                continue
            sanitized[key] = sanitize_trace_value(item, depth + 1)
        return sanitized
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        values = list(value)
        capped = values[:8]
        return [sanitize_trace_value(item, depth + 1) for item in capped]
    return _truncate_string(str(value))


def _truncate_string(value: str, limit: int = 500) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
