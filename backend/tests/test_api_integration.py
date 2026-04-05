from __future__ import annotations

from app.schemas import (
    EvidenceSnippet,
    NormalizedSource,
    QAAnswerDraft,
    QAFilters,
    QuestionIntent,
    RetrievalRoute,
    SourceType,
)
from app.services.clinicaltrials import ClinicalTrialsService
from app.services.llm_service import LLMService
from app.services.pubmed import PubMedService


def make_trial_source() -> NormalizedSource:
    snippet = EvidenceSnippet(
        snippet_id="ct_demo_1",
        source_type=SourceType.clinical_trials,
        source_id="NCT01234567",
        identifier="NCT01234567",
        title="Pembrolizumab TNBC Trial",
        section="summary",
        text="Pembrolizumab is being evaluated in recruiting adults with metastatic triple-negative breast cancer.",
        source_rank=1,
        url="https://clinicaltrials.gov/study/NCT01234567",
        published_at="2025-11-01",
    )
    return NormalizedSource(
        source_type=SourceType.clinical_trials,
        source_id="NCT01234567",
        identifier="NCT01234567",
        title="Pembrolizumab TNBC Trial",
        url="https://clinicaltrials.gov/study/NCT01234567",
        published_at="2025-11-01",
        metadata={"overall_status": "RECRUITING"},
        raw_payload={},
        snippets=[snippet],
    )


def make_pubmed_source() -> NormalizedSource:
    snippet = EvidenceSnippet(
        snippet_id="pm_demo_1",
        source_type=SourceType.pubmed,
        source_id="39876543",
        identifier="PMID:39876543",
        title="Semaglutide safety review",
        section="abstract_1",
        text="Published literature reports predominantly gastrointestinal adverse events with acceptable overall tolerability.",
        source_rank=1,
        url="https://pubmed.ncbi.nlm.nih.gov/39876543/",
        published_at="2024-07-20",
    )
    return NormalizedSource(
        source_type=SourceType.pubmed,
        source_id="39876543",
        identifier="PMID:39876543",
        title="Semaglutide safety review",
        url="https://pubmed.ncbi.nlm.nih.gov/39876543/",
        published_at="2024-07-20",
        metadata={"journal": "Journal of Clinical Metabolism"},
        raw_payload={},
        snippets=[snippet],
    )


async def _route_trials(self, question: str, filters: QAFilters) -> QuestionIntent:
    return QuestionIntent(route=RetrievalRoute.trials, focus="recruiting", filters=filters)


async def _route_pubmed(self, question: str, filters: QAFilters) -> QuestionIntent:
    return QuestionIntent(route=RetrievalRoute.pubmed, focus="safety", filters=filters)


async def _route_blended(self, question: str, filters: QAFilters) -> QuestionIntent:
    return QuestionIntent(route=RetrievalRoute.blended, focus="overview", filters=filters)


async def _trial_search(self, intent, question, filters, max_records):
    return [make_trial_source()]


async def _pubmed_search(self, intent, question, filters, max_records):
    return [make_pubmed_source()]


async def _empty_search(self, intent, question, filters, max_records):
    return []


async def _compose_trial(self, question, intent, snippets, retry_invalid=False):
    return QAAnswerDraft(
        direct_answer="A recruiting pembrolizumab trial is available.",
        why_this_answer=["A recruiting ClinicalTrials.gov record directly matches the question."],
        limitations=[],
        citation_ids=["ct_demo_1"],
    )


async def _compose_pubmed(self, question, intent, snippets, retry_invalid=False):
    return QAAnswerDraft(
        direct_answer="Published evidence suggests tolerability is generally acceptable.",
        why_this_answer=["The top PubMed abstract emphasizes common gastrointestinal adverse events."],
        limitations=[],
        citation_ids=["pm_demo_1"],
    )


async def _compose_blended(self, question, intent, snippets, retry_invalid=False):
    return QAAnswerDraft(
        direct_answer="The therapy has ongoing trials and published background evidence.",
        why_this_answer=[
            "ClinicalTrials.gov shows active recruitment.",
            "PubMed provides published safety and efficacy context.",
        ],
        limitations=[],
        citation_ids=["ct_demo_1", "pm_demo_1"],
    )


async def _compose_failure(self, question, intent, snippets, retry_invalid=False):
    raise RuntimeError("openai down")


async def _no_embeddings(self, session, texts):
    return None


def test_trials_first_flow(client, monkeypatch):
    monkeypatch.setattr(LLMService, "chat_configured", property(lambda self: True))
    monkeypatch.setattr(LLMService, "extract_intent", _route_trials)
    monkeypatch.setattr(LLMService, "compose_answer", _compose_trial)
    monkeypatch.setattr(LLMService, "embed_texts", _no_embeddings)
    monkeypatch.setattr(ClinicalTrialsService, "search", _trial_search)
    monkeypatch.setattr(PubMedService, "search", _empty_search)

    response = client.post(
        "/api/qa",
        json={"question": "Recruiting pembrolizumab trials in TNBC", "filters": {}, "max_sources": 6},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["route"] == "trials"
    assert payload["citations"][0]["identifier"] == "NCT01234567"
    assert payload["trace"]["stages"][2]["stage_id"] == "clinical_trials_retrieval"
    assert payload["trace"]["stages"][2]["status"] == "success"
    assert payload["trace"]["stages"][3]["status"] == "skipped"


def test_pubmed_first_flow(client, monkeypatch):
    monkeypatch.setattr(LLMService, "chat_configured", property(lambda self: True))
    monkeypatch.setattr(LLMService, "extract_intent", _route_pubmed)
    monkeypatch.setattr(LLMService, "compose_answer", _compose_pubmed)
    monkeypatch.setattr(LLMService, "embed_texts", _no_embeddings)
    monkeypatch.setattr(ClinicalTrialsService, "search", _empty_search)
    monkeypatch.setattr(PubMedService, "search", _pubmed_search)

    response = client.post(
        "/api/qa",
        json={"question": "What does the literature say about semaglutide safety?", "filters": {}, "max_sources": 6},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["route"] == "pubmed"
    assert payload["citations"][0]["identifier"] == "PMID:39876543"
    assert payload["trace"]["stages"][3]["stage_id"] == "pubmed_retrieval"
    assert payload["trace"]["stages"][3]["status"] == "success"


def test_blended_flow(client, monkeypatch):
    monkeypatch.setattr(LLMService, "chat_configured", property(lambda self: True))
    monkeypatch.setattr(LLMService, "extract_intent", _route_blended)
    monkeypatch.setattr(LLMService, "compose_answer", _compose_blended)
    monkeypatch.setattr(LLMService, "embed_texts", _no_embeddings)
    monkeypatch.setattr(ClinicalTrialsService, "search", _trial_search)
    monkeypatch.setattr(PubMedService, "search", _pubmed_search)

    response = client.post(
        "/api/qa",
        json={"question": "What trials are ongoing and what evidence exists?", "filters": {}, "max_sources": 6},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["route"] == "blended"
    assert sorted(payload["source_groups"].keys()) == ["clinical_trials", "pubmed"]
    assert payload["trace"]["stages"][2]["status"] == "success"
    assert payload["trace"]["stages"][3]["status"] == "success"


def test_no_results_flow(client, monkeypatch):
    monkeypatch.setattr(LLMService, "extract_intent", _route_blended)
    monkeypatch.setattr(LLMService, "embed_texts", _no_embeddings)
    monkeypatch.setattr(ClinicalTrialsService, "search", _empty_search)
    monkeypatch.setattr(PubMedService, "search", _empty_search)

    response = client.post(
        "/api/qa",
        json={"question": "A very obscure condition with no results", "filters": {}, "max_sources": 6},
    )
    payload = response.json()
    assert response.status_code == 200
    assert "could not find enough relevant" in payload["direct_answer"].lower()
    assert payload["degraded"] is True
    assert payload["trace"]["summary"]["degraded"] is True
    assert payload["trace"]["stages"][5]["status"] == "warning"
    assert payload["trace"]["stages"][7]["status"] == "warning"


def test_openai_failure_falls_back(client, monkeypatch):
    monkeypatch.setattr(LLMService, "chat_configured", property(lambda self: True))
    monkeypatch.setattr(LLMService, "extract_intent", _route_trials)
    monkeypatch.setattr(LLMService, "compose_answer", _compose_failure)
    monkeypatch.setattr(LLMService, "embed_texts", _no_embeddings)
    monkeypatch.setattr(ClinicalTrialsService, "search", _trial_search)
    monkeypatch.setattr(PubMedService, "search", _empty_search)

    response = client.post(
        "/api/qa",
        json={"question": "Recruiting pembrolizumab trials in TNBC", "filters": {}, "max_sources": 6},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["degraded"] is True
    assert payload["citations"][0]["identifier"] == "NCT01234567"


def test_health_reports_provider_neutral_status(client):
    response = client.get("/api/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["chat_provider"] in {"openai", "vllm", "none"}
    assert payload["embedding_provider"] in {"openai", "vllm", "none"}
    assert "openai_configured" not in payload


def test_no_result_responses_are_not_cached(client, monkeypatch):
    monkeypatch.setattr(LLMService, "extract_intent", _route_blended)
    monkeypatch.setattr(LLMService, "embed_texts", _no_embeddings)
    monkeypatch.setattr(ClinicalTrialsService, "search", _empty_search)
    monkeypatch.setattr(PubMedService, "search", _empty_search)

    first = client.post(
        "/api/qa",
        json={"question": "A very obscure condition with no results", "filters": {}, "max_sources": 6},
    ).json()
    second = client.post(
        "/api/qa",
        json={"question": "A very obscure condition with no results", "filters": {}, "max_sources": 6},
    ).json()

    assert first["cached"] is False
    assert second["cached"] is False


def test_cache_hit_trace_marks_cache_stage(client, monkeypatch):
    monkeypatch.setattr(LLMService, "chat_configured", property(lambda self: True))
    monkeypatch.setattr(LLMService, "extract_intent", _route_trials)
    monkeypatch.setattr(LLMService, "compose_answer", _compose_trial)
    monkeypatch.setattr(LLMService, "embed_texts", _no_embeddings)
    monkeypatch.setattr(ClinicalTrialsService, "search", _trial_search)
    monkeypatch.setattr(PubMedService, "search", _empty_search)

    first = client.post(
        "/api/qa",
        json={"question": "Recruiting pembrolizumab trials in TNBC", "filters": {}, "max_sources": 6},
    ).json()
    second = client.post(
        "/api/qa",
        json={"question": "Recruiting pembrolizumab trials in TNBC", "filters": {}, "max_sources": 6},
    ).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["trace"]["summary"]["cache_hit"] is True
    assert second["trace"]["stages"][0]["stage_id"] == "cache"
    assert second["trace"]["stages"][0]["metrics"]["cache_hit"] is True
