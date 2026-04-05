from __future__ import annotations

from app.schemas import QAFilters, QuestionIntent, RetrievalRoute
from app.services.pubmed import (
    _normalize_pubmed_record,
    _parse_abstracts,
    build_search_term,
    infer_pubmed_terms,
)

from conftest import load_fixture


def test_build_search_term_adds_recent_filter():
    intent = QuestionIntent(
        route=RetrievalRoute.pubmed,
        focus="safety",
        condition_terms=["obesity"],
        intervention_terms=["semaglutide"],
        outcome_terms=["safety"],
        filters=QAFilters(recent_literature_only=True),
    )
    query = build_search_term(intent, "semaglutide safety question", intent.filters)
    assert '"obesity"[Title/Abstract]' in query
    assert '"semaglutide"[Title/Abstract]' in query
    assert 'Date - Publication' in query


def test_infer_pubmed_terms_from_question():
    intervention_terms, condition_terms, outcome_terms = infer_pubmed_terms(
        "What does the published literature say about the safety of semaglutide in adults with obesity?",
        "published evidence",
    )
    assert intervention_terms == ["semaglutide"]
    assert condition_terms == ["adults with obesity"]
    assert outcome_terms == ["safety"]


def test_build_search_term_uses_safe_inferred_terms_when_intent_terms_are_empty():
    intent = QuestionIntent(
        route=RetrievalRoute.pubmed,
        focus="published evidence",
        filters=QAFilters(),
    )
    query = build_search_term(
        intent,
        "What does the published literature say about the safety of semaglutide in adults with obesity?",
        intent.filters,
    )
    assert '"semaglutide"[Title/Abstract]' in query
    assert '"adults with obesity"[Title/Abstract]' in query
    assert '"safety"[Title/Abstract]' in query
    assert "What does the published literature say" not in query


def test_build_search_term_handles_blended_car_t_question():
    intent = QuestionIntent(
        route=RetrievalRoute.blended,
        focus="CAR-T therapy in multiple myeloma",
        filters=QAFilters(),
    )
    query = build_search_term(
        intent,
        "What trials are ongoing for CAR-T therapy in multiple myeloma and what published evidence already exists?",
        intent.filters,
    )
    assert '"car-t therapy"[Title/Abstract]' in query
    assert '"multiple myeloma"[Title/Abstract]' in query
    assert "already exists" not in query
    assert '"trials"[Title/Abstract]' not in query


def test_parse_and_normalize_pubmed_record():
    abstracts = _parse_abstracts(load_fixture("pubmed_fetch.xml"))
    summary = load_fixture("pubmed_summary.json")["result"]["39876543"]
    source = _normalize_pubmed_record("39876543", summary, abstracts["39876543"], rank=0)
    assert source.identifier == "PMID:39876543"
    assert source.metadata["journal"] == "Journal of Clinical Metabolism"
    assert any(snippet.section.startswith("abstract_") for snippet in source.snippets)
