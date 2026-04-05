from __future__ import annotations

import pytest
from sqlmodel import Session

from app.database import engine
from app.schemas import EvidenceSnippet, QAAnswerDraft, SourceType
from app.services.qa import QAService, normalize_citation_ids, validate_citation_ids
from app.services.rerank import HybridReranker


class StubLLMService:
    async def embed_texts(self, session: Session, texts: list[str]):
        return [
            [1.0, 0.0],
            [0.9, 0.1],
            [0.0, 1.0],
        ]


@pytest.mark.asyncio
async def test_hybrid_reranker_prefers_better_match():
    reranker = HybridReranker(StubLLMService())  # type: ignore[arg-type]
    snippets = [
        EvidenceSnippet(
            snippet_id="s1",
            source_type=SourceType.pubmed,
            source_id="1",
            identifier="PMID:1",
            title="Paper one",
            section="abstract_1",
            text="semaglutide obesity safety and tolerability",
            source_rank=1,
            url="https://example.com/1",
        ),
        EvidenceSnippet(
            snippet_id="s2",
            source_type=SourceType.pubmed,
            source_id="2",
            identifier="PMID:2",
            title="Paper two",
            section="abstract_1",
            text="completely unrelated cardiology paper",
            source_rank=2,
            url="https://example.com/2",
        ),
    ]
    with Session(engine) as session:
        ranked = await reranker.rerank(session, "semaglutide safety in obesity", snippets, 2)
    assert ranked[0].snippet_id == "s1"


@pytest.mark.asyncio
async def test_hybrid_reranker_limits_per_source_concentration():
    reranker = HybridReranker(StubNoEmbeddingLLMService())  # type: ignore[arg-type]
    snippets = [
        EvidenceSnippet(
            snippet_id="s1",
            source_type=SourceType.pubmed,
            source_id="1",
            identifier="PMID:1",
            title="Paper one",
            section="title",
            text="car-t multiple myeloma",
            source_rank=1,
            url="https://example.com/1",
        ),
        EvidenceSnippet(
            snippet_id="s2",
            source_type=SourceType.pubmed,
            source_id="1",
            identifier="PMID:1",
            title="Paper one",
            section="abstract_1",
            text="car-t multiple myeloma response",
            source_rank=1,
            url="https://example.com/1",
        ),
        EvidenceSnippet(
            snippet_id="s3",
            source_type=SourceType.pubmed,
            source_id="1",
            identifier="PMID:1",
            title="Paper one",
            section="abstract_2",
            text="car-t multiple myeloma safety",
            source_rank=1,
            url="https://example.com/1",
        ),
        EvidenceSnippet(
            snippet_id="s4",
            source_type=SourceType.pubmed,
            source_id="2",
            identifier="PMID:2",
            title="Paper two",
            section="abstract_1",
            text="multiple myeloma car-t trial",
            source_rank=2,
            url="https://example.com/2",
        ),
    ]
    with Session(engine) as session:
        ranked = await reranker.rerank(session, "car-t therapy in multiple myeloma", snippets, 3)

    assert [snippet.source_id for snippet in ranked].count("1") == 2
    assert any(snippet.source_id == "2" for snippet in ranked)


class StubNoEmbeddingLLMService:
    async def embed_texts(self, session: Session, texts: list[str]):
        return None


@pytest.mark.asyncio
async def test_hybrid_reranker_renormalizes_when_embeddings_are_disabled():
    reranker = HybridReranker(StubNoEmbeddingLLMService())  # type: ignore[arg-type]
    snippets = [
        EvidenceSnippet(
            snippet_id="s1",
            source_type=SourceType.pubmed,
            source_id="1",
            identifier="PMID:1",
            title="Paper one",
            section="abstract_1",
            text="semaglutide safety obesity",
            source_rank=1,
            url="https://example.com/1",
        ),
        EvidenceSnippet(
            snippet_id="s2",
            source_type=SourceType.pubmed,
            source_id="2",
            identifier="PMID:2",
            title="Paper two",
            section="abstract_1",
            text="unrelated cardiology paper",
            source_rank=1,
            url="https://example.com/2",
        ),
    ]
    with Session(engine) as session:
        ranked = await reranker.rerank(session, "semaglutide safety obesity", snippets, 2)

    assert ranked[0].snippet_id == "s1"
    assert ranked[0].score == 1.0
    assert ranked[1].score == 0.5


def test_validate_citation_ids_requires_supported_snippets():
    snippets = [
        EvidenceSnippet(
            snippet_id="s1",
            source_type=SourceType.clinical_trials,
            source_id="NCT1",
            identifier="NCT1",
            title="Trial one",
            section="summary",
            text="trial text",
            source_rank=1,
            url="https://example.com",
        )
    ]
    assert validate_citation_ids(
        QAAnswerDraft(
            direct_answer="answer",
            why_this_answer=["because"],
            limitations=[],
            citation_ids=["s1"],
        ),
        snippets,
    )
    assert not validate_citation_ids(
        QAAnswerDraft(
            direct_answer="answer",
            why_this_answer=["because"],
            limitations=[],
            citation_ids=["missing"],
        ),
        snippets,
    )


def test_normalize_citation_ids_maps_pubmed_source_ids_to_snippet_ids():
    snippets = [
        EvidenceSnippet(
            snippet_id="pm_title",
            source_type=SourceType.pubmed,
            source_id="36216945",
            identifier="PMID:36216945",
            title="Paper one",
            section="title",
            text="title text",
            source_rank=1,
            url="https://example.com/1",
        ),
        EvidenceSnippet(
            snippet_id="pm_abs",
            source_type=SourceType.pubmed,
            source_id="40353578",
            identifier="PMID:40353578",
            title="Paper two",
            section="abstract_1",
            text="abstract text",
            source_rank=2,
            url="https://example.com/2",
        ),
    ]
    normalized = normalize_citation_ids(
        QAAnswerDraft(
            direct_answer="answer",
            why_this_answer=["because"],
            limitations=[],
            citation_ids=["PMID:36216945", "40353578"],
        ),
        snippets,
    )
    assert normalized.citation_ids == ["pm_title", "pm_abs"]


def test_select_citations_deduplicates_repeated_ids_and_sources():
    snippet = EvidenceSnippet(
        snippet_id="s1",
        source_type=SourceType.clinical_trials,
        source_id="NCT1",
        identifier="NCT1",
        title="Trial one",
        section="summary",
        text="trial text",
        source_rank=1,
        url="https://example.com",
    )
    second_snippet_same_source = EvidenceSnippet(
        snippet_id="s2",
        source_type=SourceType.clinical_trials,
        source_id="NCT1",
        identifier="NCT1",
        title="Trial one",
        section="status",
        text="status text",
        source_rank=1,
        url="https://example.com",
    )
    service = QAService(None, None, None, None)  # type: ignore[arg-type]
    citations = service._select_citations(
        QAAnswerDraft(
            direct_answer="answer",
            why_this_answer=["because"],
            limitations=[],
            citation_ids=["s1", "s1", "s2"],
        ),
        [snippet, second_snippet_same_source],
    )
    assert len(citations) == 1
