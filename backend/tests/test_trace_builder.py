from __future__ import annotations

from app.schemas import RetrievalRoute
from app.services.trace_builder import build_pipeline_trace, make_stage, sanitize_trace_value


def test_build_pipeline_trace_emits_all_stages_in_order():
    trace = build_pipeline_trace(
        route=RetrievalRoute.pubmed,
        stages=[
            make_stage("cache", status="success", summary="cache"),
            make_stage("intent", status="success", summary="intent"),
            make_stage("pubmed_retrieval", status="success", summary="pubmed"),
            make_stage("final_response", status="success", summary="final"),
        ],
        degraded=False,
        degraded_reason=None,
        cache_hit=False,
        total_ms=123.4,
    )

    assert [stage.stage_id for stage in trace.stages] == [
        "cache",
        "intent",
        "clinical_trials_retrieval",
        "pubmed_retrieval",
        "rerank",
        "answer_generation",
        "citation_validation",
        "final_response",
    ]
    assert trace.stages[2].status == "skipped"


def test_sanitize_trace_value_truncates_strings_and_caps_arrays():
    payload = {
        "text": "x" * 700,
        "items": list(range(20)),
        "api_key": "secret",
    }
    sanitized = sanitize_trace_value(payload)

    assert len(sanitized["text"]) == 500
    assert len(sanitized["items"]) == 8
    assert "api_key" not in sanitized
