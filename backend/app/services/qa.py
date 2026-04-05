from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict

from sqlmodel import Session

from ..config import settings
from ..schemas import (
    Citation,
    EvidenceSnippet,
    NormalizedSource,
    PipelineTrace,
    QAAnswerDraft,
    QARequest,
    QAResponse,
    QuestionIntent,
)
from .cache import (
    build_query_cache_key,
    cleanup_expired,
    get_cached_response,
    record_request_trace,
    set_cached_response,
    upsert_source_document,
)
from .clinicaltrials import ClinicalTrialsService, build_search_plan
from .llm_service import LLMService
from .pubmed import PubMedService, build_search_term
from .rerank import HybridReranker
from .trace_builder import (
    answer_preview,
    build_pipeline_trace,
    card,
    citations_preview,
    make_stage,
    snippet_preview,
    source_preview,
)


logger = logging.getLogger(__name__)


def validate_citation_ids(answer: QAAnswerDraft, snippets: list[EvidenceSnippet]) -> bool:
    allowed = {snippet.snippet_id for snippet in snippets}
    if not answer.citation_ids:
        return False
    return all(citation_id in allowed for citation_id in answer.citation_ids)


def normalize_citation_ids(
    answer: QAAnswerDraft,
    snippets: list[EvidenceSnippet],
) -> QAAnswerDraft:
    if not answer.citation_ids:
        return answer

    snippet_ids = {snippet.snippet_id for snippet in snippets}
    source_lookup: dict[str, str] = {}
    for snippet in snippets:
        candidate_keys = {
            snippet.source_id,
            snippet.identifier,
        }
        if snippet.identifier.startswith("PMID:"):
            candidate_keys.add(snippet.identifier.removeprefix("PMID:"))
        for key in candidate_keys:
            cleaned = str(key).strip().lower()
            if cleaned and cleaned not in source_lookup:
                source_lookup[cleaned] = snippet.snippet_id

    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for citation_id in answer.citation_ids:
        raw_id = str(citation_id).strip()
        if not raw_id:
            continue
        mapped_id = raw_id if raw_id in snippet_ids else source_lookup.get(raw_id.lower(), raw_id)
        if mapped_id in snippet_ids and mapped_id not in seen_ids:
            seen_ids.add(mapped_id)
            normalized_ids.append(mapped_id)

    return answer.model_copy(update={"citation_ids": normalized_ids})


def build_citation(snippet: EvidenceSnippet) -> Citation:
    return Citation(
        snippet_id=snippet.snippet_id,
        source_type=snippet.source_type,
        source_id=snippet.source_id,
        identifier=snippet.identifier,
        title=snippet.title,
        section=snippet.section,
        text=snippet.text,
        url=snippet.url,
        published_at=snippet.published_at,
        score=snippet.score,
    )


def build_grouped_citations(citations: list[Citation]) -> dict[str, list[Citation]]:
    grouped: dict[str, list[Citation]] = defaultdict(list)
    for citation in citations:
        grouped[citation.source_type.value].append(citation)
    return dict(grouped)


def build_extractive_fallback(
    route: str,
    snippets: list[EvidenceSnippet],
    reason: str,
) -> QAAnswerDraft:
    if not snippets:
        return QAAnswerDraft(
            direct_answer=(
                "I could not find enough relevant ClinicalTrials.gov or PubMed evidence "
                "to answer this question confidently."
            ),
            why_this_answer=[],
            limitations=[reason, "No relevant source evidence was retrieved."],
            citation_ids=[],
        )

    top = snippets[: min(4, len(snippets))]
    direct_answer = (
        "Here is an extractive summary from the strongest retrieved evidence. "
        "This answer is conservative because structured synthesis was unavailable."
    )
    if route == "trials":
        direct_answer = (
            "I found relevant clinical trial records. The response below is an "
            "extractive summary grounded in those trial snippets."
        )
    elif route == "pubmed":
        direct_answer = (
            "I found relevant published literature. The response below is an "
            "extractive summary grounded in those PubMed snippets."
        )
    elif route == "blended":
        direct_answer = (
            "I found both trial and literature evidence. The response below is a "
            "conservative extractive summary across both sources."
        )

    why = [
        f"{snippet.identifier} {snippet.section}: {snippet.text[:220]}".strip()
        for snippet in top
    ]
    limitations = [reason, "PubMed evidence is abstract-grounded unless richer text is available."]
    return QAAnswerDraft(
        direct_answer=direct_answer,
        why_this_answer=why,
        limitations=limitations,
        citation_ids=[snippet.snippet_id for snippet in top],
    )


def build_answer_backfill(
    draft: QAAnswerDraft,
    intent: QuestionIntent,
    snippets: list[EvidenceSnippet],
) -> QAAnswerDraft:
    selected_ids = set(draft.citation_ids)
    support_snippets = [
        snippet for snippet in snippets if snippet.snippet_id in selected_ids
    ] or snippets[:3]

    why_this_answer = list(draft.why_this_answer)
    if not why_this_answer:
        why_this_answer = [
            f"{snippet.identifier} ({snippet.section}): {snippet.text[:180]}"
            for snippet in support_snippets[:3]
        ]

    limitations = list(draft.limitations)
    if not limitations:
        if intent.route.value in {"pubmed", "blended"}:
            limitations.append(
                "PubMed evidence is abstract-grounded unless richer full-text evidence is available."
            )
        if intent.route.value in {"trials", "blended"}:
            limitations.append(
                "ClinicalTrials.gov recruitment statuses can change; confirm the live trial record before acting."
            )
        if not limitations:
            limitations.append("This answer is limited to the retrieved evidence snippets.")

    return draft.model_copy(
        update={
            "why_this_answer": why_this_answer,
            "limitations": limitations,
        }
    )


class QAService:
    def __init__(
        self,
        llm_service: LLMService,
        clinical_trials_service: ClinicalTrialsService,
        pubmed_service: PubMedService,
        reranker: HybridReranker,
    ) -> None:
        self.llm_service = llm_service
        self.clinical_trials_service = clinical_trials_service
        self.pubmed_service = pubmed_service
        self.reranker = reranker

    async def answer(self, session: Session, payload: QARequest) -> QAResponse:
        request_id = str(uuid.uuid4())
        cleanup_at = cleanup_expired(session)
        runtime_debug = self.llm_service.debug_status()
        trace_stages = []
        cache_key = build_query_cache_key(
            payload.question,
            payload.filters.model_dump(),
            payload.max_sources,
            runtime_context=runtime_debug,
        )
        cached = get_cached_response(session, cache_key)
        if cached is not None:
            trace = self._update_cached_trace(cached.trace, cleanup_at=cleanup_at)
            response = cached.model_copy(
                update={
                    "request_id": request_id,
                    "trace": trace,
                    "cached": True,
                    "debug": {
                        **cached.debug,
                        "request_id": request_id,
                        "cache_hit": True,
                        "cache_cleanup_at": cleanup_at,
                    },
                }
            )
            record_request_trace(
                session,
                request_id=request_id,
                route=response.route.value,
                cached=True,
                degraded=response.degraded,
                source_ids=[citation.source_id for citation in response.citations],
                timings={"total_ms": 0.0, "cache": True},
            )
            logger.info(
                "qa_request cache_hit request_id=%s route=%s citations=%d",
                request_id,
                response.route.value,
                len(response.citations),
            )
            return response

        timings: dict[str, float] = {}
        total_start = time.perf_counter()
        trace_stages.append(
            make_stage(
                "cache",
                status="success",
                summary="No cached response matched this request, so the system ran a live pipeline.",
                metrics={"cache_hit": False, "cache_key_prefix": cache_key[:12]},
                raw_json={"cache_key_prefix": cache_key[:12]},
            )
        )

        intent_start = time.perf_counter()
        intent = await self.llm_service.extract_intent(
            payload.question,
            payload.filters,
        )
        timings["intent_ms"] = round((time.perf_counter() - intent_start) * 1000, 2)
        trace_stages.append(
            make_stage(
                "intent",
                status="success",
                summary=f"The question was routed to {intent.route.value} retrieval.",
                metrics={
                    "provider": self.llm_service.chat_provider_name,
                    "route": intent.route.value,
                    "focus": intent.focus,
                    "intent_ms": timings["intent_ms"],
                },
                cards=[
                    card("Route", intent.route.value),
                    card("Focus", intent.focus),
                    card(
                        "Extracted terms",
                        (
                            f"condition={intent.condition_terms or []}, "
                            f"intervention={intent.intervention_terms or []}, "
                            f"population={intent.population_terms or []}, "
                            f"outcome={intent.outcome_terms or []}"
                        ),
                    ),
                ],
                raw_json={"intent": intent.model_dump(mode="json")},
            )
        )

        retrieval_start = time.perf_counter()
        sources: list[NormalizedSource] = []
        clinical_sources: list[NormalizedSource] = []
        pubmed_sources: list[NormalizedSource] = []
        clinical_plan, _clinical_statuses = build_search_plan(
            intent,
            payload.question,
            payload.filters,
            8,
        )
        if intent.route in ("trials", "blended"):
            clinical_sources = await self.clinical_trials_service.search(
                intent=intent,
                question=payload.question,
                filters=payload.filters,
                max_records=8,
            )
            for source in clinical_sources:
                upsert_source_document(session, source, settings.clinical_trials_ttl_hours)
            sources.extend(clinical_sources)
        if intent.route in ("pubmed", "blended"):
            pubmed_sources = await self.pubmed_service.search(
                intent=intent,
                question=payload.question,
                filters=payload.filters,
                max_records=8,
            )
            for source in pubmed_sources:
                upsert_source_document(session, source, settings.pubmed_ttl_hours)
            sources.extend(pubmed_sources)
        timings["retrieval_ms"] = round((time.perf_counter() - retrieval_start) * 1000, 2)
        trace_stages.append(
            make_stage(
                "clinical_trials_retrieval",
                status=(
                    "success"
                    if clinical_sources
                    else "skipped"
                    if intent.route == "pubmed"
                    else "warning"
                ),
                summary=(
                    f"Retrieved {len(clinical_sources)} ClinicalTrials.gov source records."
                    if intent.route in ("trials", "blended")
                    else "ClinicalTrials.gov retrieval was skipped for this PubMed-only request."
                ),
                metrics={
                    "source_count": len(clinical_sources),
                    "retrieval_ms": timings["retrieval_ms"],
                },
                cards=[
                    card(source.identifier, source.title)
                    for source in clinical_sources[:4]
                ],
                raw_json={
                    "query_params": clinical_plan[0] if clinical_plan else {},
                    "fallback_query_params": clinical_plan[1] if len(clinical_plan) > 1 else {},
                    "sources": [source_preview(source) for source in clinical_sources[:4]],
                },
            )
        )
        trace_stages.append(
            make_stage(
                "pubmed_retrieval",
                status=(
                    "success"
                    if pubmed_sources
                    else "skipped"
                    if intent.route == "trials"
                    else "warning"
                ),
                summary=(
                    f"Retrieved {len(pubmed_sources)} PubMed source records."
                    if intent.route in ("pubmed", "blended")
                    else "PubMed retrieval was skipped for this ClinicalTrials-only request."
                ),
                metrics={
                    "source_count": len(pubmed_sources),
                    "retrieval_ms": timings["retrieval_ms"],
                },
                cards=[
                    card(source.identifier, source.title)
                    for source in pubmed_sources[:4]
                ],
                raw_json={
                    "search_term": build_search_term(intent, payload.question, payload.filters),
                    "sources": [source_preview(source) for source in pubmed_sources[:4]],
                },
            )
        )

        all_snippets = [snippet for source in sources for snippet in source.snippets]
        rerank_start = time.perf_counter()
        rerank_top_k = max(payload.max_sources, settings.max_sources_default)
        reranked = await self.reranker.rerank(
            session=session,
            question=payload.question,
            snippets=all_snippets,
            top_k=rerank_top_k,
        )
        timings["rerank_ms"] = round((time.perf_counter() - rerank_start) * 1000, 2)
        trace_stages.append(
            make_stage(
                "rerank",
                status="success" if reranked else "warning",
                summary=(
                    f"Reranked {len(all_snippets)} candidate snippets and kept {len(reranked)}."
                    if all_snippets
                    else "No snippets were available to rerank."
                ),
                metrics={
                    "candidate_count": len(all_snippets),
                    "top_k": rerank_top_k,
                    "returned_count": len(reranked),
                    "embeddings_enabled": self.llm_service.embeddings_enabled,
                    "rerank_ms": timings["rerank_ms"],
                },
                cards=[
                    card(
                        f"{snippet.identifier} · {snippet.section}",
                        f"score={snippet.score} · {snippet.text[:180]}",
                    )
                    for snippet in reranked[:5]
                ],
                raw_json={
                    "top_snippets": [snippet_preview(snippet) for snippet in reranked[:8]],
                },
            )
        )

        degraded = False
        degraded_reason: str | None = None
        answer_start = time.perf_counter()
        draft, answer_degraded, answer_trace = await self._build_answer(payload.question, intent, reranked)
        degraded = degraded or answer_degraded
        timings["answer_ms"] = round((time.perf_counter() - answer_start) * 1000, 2)
        trace_stages.append(
            make_stage(
                "answer_generation",
                status=answer_trace["status"],
                summary=answer_trace["summary"],
                metrics={
                    "provider": self.llm_service.chat_provider_name,
                    "answer_ms": timings["answer_ms"],
                    "attempts": answer_trace["attempts"],
                    "extractive_fallback": answer_trace["extractive_fallback"],
                },
                cards=answer_trace["cards"],
                raw_json=answer_trace["raw_json"],
            )
        )
        if not validate_citation_ids(draft, reranked):
            degraded = True
            degraded_reason = "Citation validation failed after two attempts."
            draft = build_extractive_fallback(
                intent.route.value,
                reranked,
                degraded_reason,
            )
            citation_stage = make_stage(
                "citation_validation",
                status="error",
                summary=degraded_reason,
                metrics={
                    "valid": False,
                    "cited_count": len(draft.citation_ids),
                },
                raw_json={
                    "citation_ids": draft.citation_ids,
                    "allowed_snippet_ids": [snippet.snippet_id for snippet in reranked[:8]],
                },
            )
        elif not self.llm_service.chat_configured:
            degraded = True
            degraded_reason = "The configured chat provider is unavailable."
            citation_stage = make_stage(
                "citation_validation",
                status="warning",
                summary="Citation validation was bypassed because the system used extractive fallback.",
                metrics={"valid": bool(draft.citation_ids), "cited_count": len(draft.citation_ids)},
                raw_json={"citation_ids": draft.citation_ids},
            )
        else:
            citation_stage = make_stage(
                "citation_validation",
                status="success",
                summary="All cited snippet ids matched retrieved evidence.",
                metrics={"valid": True, "cited_count": len(draft.citation_ids)},
                raw_json={"citation_ids": draft.citation_ids},
            )
        trace_stages.append(citation_stage)

        citations = self._select_citations(draft, reranked)
        if not citations:
            degraded = True
            degraded_reason = "No valid citations were available for the generated answer."
            draft = build_extractive_fallback(
                intent.route.value,
                reranked,
                degraded_reason,
            )
            citations = self._select_citations(draft, reranked)
        if degraded_reason is None and answer_degraded:
            degraded_reason = answer_trace["summary"]

        timings["total_ms"] = round((time.perf_counter() - total_start) * 1000, 2)
        debug = {
            "request_id": request_id,
            "cache_hit": False,
            "cache_cleanup_at": cleanup_at,
            **runtime_debug,
            "source_counts": {
                "clinical_trials": len(
                    {source.source_id for source in sources if source.source_type.value == "clinical_trials"}
                ),
                "pubmed": len(
                    {source.source_id for source in sources if source.source_type.value == "pubmed"}
                ),
            },
            "snippet_count": len(reranked),
            "timings_ms": timings,
        }
        trace_stages.append(
            make_stage(
                "final_response",
                status="warning" if degraded else "success",
                summary=(
                    degraded_reason
                    if degraded_reason
                    else f"Built a final response with {len(citations)} citations."
                ),
                metrics={
                    "degraded": degraded,
                    "citation_count": len(citations),
                    "route": intent.route.value,
                    "total_ms": timings["total_ms"],
                },
                cards=[
                    card(citation.identifier, f"{citation.section} · {citation.title}")
                    for citation in citations[:6]
                ],
                raw_json={
                    "citations": citations_preview(citations),
                    "direct_answer": draft.direct_answer,
                    "limitations": draft.limitations,
                },
            )
        )
        trace = build_pipeline_trace(
            route=intent.route,
            stages=trace_stages,
            degraded=degraded,
            degraded_reason=degraded_reason,
            cache_hit=False,
            total_ms=timings["total_ms"],
        )
        response = QAResponse(
            request_id=request_id,
            direct_answer=draft.direct_answer,
            why_this_answer=draft.why_this_answer,
            limitations=draft.limitations,
            citations=citations,
            source_groups=build_grouped_citations(citations),
            route=intent.route,
            cached=False,
            degraded=degraded,
            trace=trace,
            debug=debug,
        )
        if reranked or citations:
            set_cached_response(session, cache_key, response, settings.query_cache_ttl_hours)
        record_request_trace(
            session=session,
            request_id=request_id,
            route=intent.route.value,
            cached=False,
            degraded=degraded,
            source_ids=sorted({citation.source_id for citation in citations}),
            timings=timings,
        )
        logger.info(
            "qa_request request_id=%s route=%s degraded=%s sources=%d citations=%d",
            request_id,
            intent.route.value,
            degraded,
            len(sources),
            len(citations),
        )
        return response

    async def _build_answer(
        self,
        question: str,
        intent: QuestionIntent,
        reranked: list[EvidenceSnippet],
    ) -> tuple[QAAnswerDraft, bool, dict]:
        if not reranked:
            return (
                build_extractive_fallback(
                    intent.route.value,
                    reranked,
                    "No relevant evidence was retrieved.",
                ),
                True,
                {
                    "status": "warning",
                    "summary": "No reranked evidence was available, so the system returned an extractive fallback.",
                    "attempts": 0,
                    "extractive_fallback": True,
                    "cards": [],
                    "raw_json": {},
                },
            )
        if not self.llm_service.chat_configured:
            return (
                build_extractive_fallback(
                    intent.route.value,
                    reranked,
                    "The configured chat provider is unavailable, so the system returned an extractive answer.",
                ),
                True,
                {
                    "status": "warning",
                    "summary": "The configured chat provider was unavailable, so the system used extractive fallback.",
                    "attempts": 0,
                    "extractive_fallback": True,
                    "cards": [],
                    "raw_json": {},
                },
            )

        evidence_payload = [
            {
                "snippet_id": snippet.snippet_id,
                "source_type": snippet.source_type.value,
                "source_id": snippet.source_id,
                "identifier": snippet.identifier,
                "title": snippet.title,
                "section": snippet.section,
                "published_at": snippet.published_at,
                "text": snippet.text[:900],
            }
            for snippet in reranked
        ]
        attempts = 0
        for attempt in range(2):
            attempts += 1
            try:
                draft = await self.llm_service.compose_answer(
                    question=question,
                    intent=intent,
                    snippets=evidence_payload,
                    retry_invalid=attempt == 1,
                )
            except Exception:
                continue
            draft = normalize_citation_ids(draft, reranked)
            if validate_citation_ids(draft, reranked):
                draft = build_answer_backfill(draft, intent, reranked)
                return (
                    draft,
                    False,
                    {
                        "status": "success",
                        "summary": "Structured answer generation succeeded with valid citation ids.",
                        "attempts": attempts,
                        "extractive_fallback": False,
                        "cards": [
                            card("Direct answer", draft.direct_answer),
                            card("Citation ids", ", ".join(draft.citation_ids) or "None"),
                        ],
                        "raw_json": {"draft": answer_preview(draft)},
                    },
                )
        return (
            build_extractive_fallback(
                intent.route.value,
                reranked,
                "Structured generation failed or returned unsupported citations.",
            ),
            True,
            {
                "status": "warning",
                "summary": "Structured generation failed or returned unsupported citations, so the system fell back to extractive mode.",
                "attempts": attempts,
                "extractive_fallback": True,
                "cards": [],
                "raw_json": {"evidence_preview": evidence_payload[:4]},
            },
        )

    def _select_citations(
        self,
        draft: QAAnswerDraft,
        reranked: list[EvidenceSnippet],
    ) -> list[Citation]:
        snippet_lookup = {snippet.snippet_id: snippet for snippet in reranked}
        selected_ids = draft.citation_ids or [snippet.snippet_id for snippet in reranked[:4]]
        seen_ids: set[str] = set()
        seen_sources: set[tuple[str, str]] = set()
        citations: list[Citation] = []
        for snippet_id in selected_ids:
            if snippet_id in seen_ids:
                continue
            snippet = snippet_lookup.get(snippet_id)
            if snippet is None:
                continue
            source_key = (snippet.source_type.value, snippet.source_id)
            if source_key in seen_sources:
                continue
            seen_ids.add(snippet_id)
            seen_sources.add(source_key)
            citations.append(build_citation(snippet))
        return citations

    def _update_cached_trace(
        self,
        trace: PipelineTrace,
        *,
        cleanup_at: str,
    ) -> PipelineTrace:
        stages = [stage.model_copy(deep=True) for stage in trace.stages]
        if stages:
            stages[0] = stages[0].model_copy(
                update={
                    "status": "success",
                    "summary": "A cached response matched this request, so the live pipeline was skipped.",
                    "metrics": {
                        **stages[0].metrics,
                        "cache_hit": True,
                        "cache_cleanup_at": cleanup_at,
                    },
                }
            )
        return trace.model_copy(
            update={
                "summary": trace.summary.model_copy(update={"cache_hit": True}),
                "stages": stages,
            }
        )
