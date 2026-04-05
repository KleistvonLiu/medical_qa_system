from __future__ import annotations

import math
from typing import Sequence

from sqlmodel import Session

from ..schemas import EvidenceSnippet
from .llm_service import LLMService
from .text_utils import keyword_overlap


def cosine_similarity(first: Sequence[float], second: Sequence[float]) -> float:
    if not first or not second or len(first) != len(second):
        return 0.0
    numerator = sum(a * b for a, b in zip(first, second))
    first_norm = math.sqrt(sum(a * a for a in first))
    second_norm = math.sqrt(sum(b * b for b in second))
    if not first_norm or not second_norm:
        return 0.0
    return numerator / (first_norm * second_norm)


class HybridReranker:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    async def rerank(
        self,
        session: Session,
        question: str,
        snippets: list[EvidenceSnippet],
        top_k: int,
    ) -> list[EvidenceSnippet]:
        if not snippets:
            return []

        vectors = await self.llm_service.embed_texts(
            session,
            [question, *[snippet.text for snippet in snippets]],
        )
        query_vector = vectors[0] if vectors else []
        snippet_vectors = vectors[1:] if vectors else []
        has_embeddings = bool(vectors and query_vector and len(snippet_vectors) == len(snippets))

        weight_pairs = {
            "source": 0.35,
            "keyword": 0.35,
            "embedding": 0.30 if has_embeddings else 0.0,
        }
        weight_total = sum(weight_pairs.values()) or 1.0

        ranked: list[EvidenceSnippet] = []
        for index, snippet in enumerate(snippets):
            source_component = max(0.1, 1.0 - ((snippet.source_rank - 1) / 8.0))
            keyword_component = keyword_overlap(question, snippet.text)
            embedding_component = 0.0
            if has_embeddings and index < len(snippet_vectors):
                embedding_component = cosine_similarity(query_vector, snippet_vectors[index])
            score = (
                (weight_pairs["source"] / weight_total) * source_component
                + (weight_pairs["keyword"] / weight_total) * keyword_component
                + (weight_pairs["embedding"] / weight_total) * embedding_component
            )
            ranked.append(snippet.model_copy(update={"score": round(score, 6)}))

        ranked.sort(key=lambda item: item.score, reverse=True)
        return self._select_diverse_top_k(ranked, top_k)

    def _select_diverse_top_k(
        self,
        ranked: list[EvidenceSnippet],
        top_k: int,
        *,
        max_per_source: int = 2,
    ) -> list[EvidenceSnippet]:
        selected: list[EvidenceSnippet] = []
        source_counts: dict[tuple[str, str], int] = {}
        overflow: list[EvidenceSnippet] = []

        for snippet in ranked:
            source_key = (snippet.source_type.value, snippet.source_id)
            current_count = source_counts.get(source_key, 0)
            if current_count < max_per_source:
                selected.append(snippet)
                source_counts[source_key] = current_count + 1
            else:
                overflow.append(snippet)
            if len(selected) >= top_k:
                return selected

        for snippet in overflow:
            selected.append(snippet)
            if len(selected) >= top_k:
                break
        return selected
