from __future__ import annotations

import pytest

from app.schemas import QAFilters, QuestionIntent, RetrievalRoute
from app.services.clinicaltrials import (
    ClinicalTrialsService,
    build_fallback_search_params,
    build_search_plan,
    build_search_params,
    infer_desired_statuses,
    normalize_study,
)

from conftest import load_fixture


def test_build_search_params_prefers_structured_fields():
    intent = QuestionIntent(
        route=RetrievalRoute.trials,
        focus="recruiting",
        condition_terms=["triple-negative breast cancer"],
        intervention_terms=["pembrolizumab"],
        filters=QAFilters(recruiting_only=True),
    )
    params = build_search_params(intent, "question text", 8)
    assert params["query.cond"] == "triple-negative breast cancer"
    assert params["query.intr"] == "pembrolizumab"
    assert params["pageSize"] == 8
    assert "question text" not in str(params)


def test_build_search_params_derives_trial_terms_from_question():
    intent = QuestionIntent(
        route=RetrievalRoute.trials,
        focus="recruiting",
        filters=QAFilters(),
    )
    params = build_search_params(
        intent,
        "Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?",
        8,
    )
    assert params["query.intr"] == "pembrolizumab"
    assert params["query.cond"] == "metastatic triple-negative breast cancer"


def test_build_fallback_search_params_uses_safe_keyword_query():
    params = build_fallback_search_params(
        "What trials are ongoing for CAR-T therapy in multiple myeloma and what evidence already exists?",
        8,
    )
    assert params["pageSize"] == 8
    assert "query.term" in params
    assert "what" not in params["query.term"]


def test_build_search_params_strips_follow_up_clause_for_blended_question():
    intent = QuestionIntent(
        route=RetrievalRoute.blended,
        focus="overview",
        filters=QAFilters(),
    )
    params = build_search_params(
        intent,
        "What trials are ongoing for CAR-T therapy in multiple myeloma and what published evidence already exists?",
        8,
    )
    assert params["query.intr"] == "car-t therapy"
    assert params["query.cond"] == "multiple myeloma"


def test_infer_desired_statuses_handles_recruiting_and_ongoing_questions():
    assert infer_desired_statuses(
        "Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?",
        QAFilters(),
    ) == {"RECRUITING"}
    assert infer_desired_statuses(
        "What trials are ongoing for CAR-T therapy in multiple myeloma?",
        QAFilters(),
    ) == {
        "RECRUITING",
        "ACTIVE_NOT_RECRUITING",
        "NOT_YET_RECRUITING",
        "ENROLLING_BY_INVITATION",
    }


def test_build_search_plan_adds_recruiting_filter_and_expands_page_size():
    intent = QuestionIntent(
        route=RetrievalRoute.trials,
        focus="recruiting_trials",
        filters=QAFilters(recruiting_only=True),
    )
    plan, statuses = build_search_plan(
        intent,
        "Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?",
        QAFilters(recruiting_only=True),
        8,
    )
    assert statuses == {"RECRUITING"}
    assert plan[0]["pageSize"] == 20
    assert plan[0]["filter.overallStatus"] == "RECRUITING"


async def _failing_fetch(self, params):
    raise ValueError("boom")


@pytest.mark.asyncio
async def test_search_returns_empty_when_fetch_fails():
    service = ClinicalTrialsService()
    service._fetch = _failing_fetch.__get__(service, ClinicalTrialsService)
    results = await service.search(
        QuestionIntent(route=RetrievalRoute.trials, focus="recruiting", filters=QAFilters()),
        "Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?",
        QAFilters(),
        8,
    )
    assert results == []


def test_normalize_study_builds_snippets():
    payload = load_fixture("clinicaltrials_response.json")
    source = normalize_study(payload["studies"][0], rank=0)
    assert source is not None
    assert source.source_id == "NCT01234567"
    assert source.metadata["overall_status"] == "RECRUITING"
    sections = {snippet.section for snippet in source.snippets}
    assert {"status", "summary", "eligibility", "outcomes"} <= sections
