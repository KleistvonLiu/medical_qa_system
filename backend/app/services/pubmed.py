from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings
from ..schemas import EvidenceSnippet, NormalizedSource, QAFilters, QuestionIntent, SourceType
from .text_utils import compact_text, split_sentences, stable_id, tokenize


GENERIC_PUBMED_TOKENS = {
    "what",
    "does",
    "published",
    "publish",
    "literature",
    "paper",
    "papers",
    "study",
    "studies",
    "evidence",
    "say",
    "about",
    "adults",
    "adult",
    "patients",
    "patient",
    "trials",
    "trial",
    "ongoing",
    "already",
    "exists",
    "exist",
}

FOLLOW_UP_CLAUSE = re.compile(
    r"\s+and\s+(what\s+)?(published\s+)?(evidence|literature|results?)\b.*$",
    re.IGNORECASE,
)


def _quoted_title_abstract(term: str) -> str:
    return f'"{term}"[Title/Abstract]'


def _safe_keyword_tokens(question: str) -> list[str]:
    return [token for token in tokenize(question) if token not in GENERIC_PUBMED_TOKENS]


def _strip_follow_up_clause(text: str) -> str:
    return FOLLOW_UP_CLAUSE.sub("", text).strip(" ,.;:")


def infer_pubmed_terms(question: str, focus: str) -> tuple[list[str], list[str], list[str]]:
    normalized = re.sub(r"\s+", " ", question.strip().rstrip("?")).lower()
    intervention_terms: list[str] = []
    condition_terms: list[str] = []
    outcome_terms: list[str] = []

    phrasal_match = re.search(r"\b(?:of|for)\s+(.+?)\s+in\s+(.+)$", normalized)
    if phrasal_match:
        intervention_terms.append(_strip_follow_up_clause(phrasal_match.group(1)))
        condition_terms.append(_strip_follow_up_clause(phrasal_match.group(2)))

    if "safety" in normalized or "adverse" in normalized or focus == "safety":
        outcome_terms.append("safety")
    elif "efficacy" in normalized or "effective" in normalized or focus == "efficacy":
        outcome_terms.append("efficacy")
    elif "published evidence" in focus or "literature" in normalized:
        outcome_terms = outcome_terms

    if not intervention_terms and not condition_terms:
        safe_tokens = _safe_keyword_tokens(question)
        if safe_tokens:
            intervention_terms.extend(safe_tokens[:2])
            if len(safe_tokens) > 2:
                condition_terms.extend(safe_tokens[2:5])

    intervention_terms = [term for term in intervention_terms if term]
    condition_terms = [term for term in condition_terms if term]
    return intervention_terms, condition_terms, outcome_terms


def build_search_term(intent: QuestionIntent, question: str, filters: QAFilters) -> str:
    condition_terms = list(intent.condition_terms)
    intervention_terms = list(intent.intervention_terms)
    outcome_terms = list(intent.outcome_terms)

    inferred_interventions, inferred_conditions, inferred_outcomes = infer_pubmed_terms(
        question,
        intent.focus,
    )
    if not condition_terms:
        condition_terms = inferred_conditions
    if not intervention_terms:
        intervention_terms = inferred_interventions
    if not outcome_terms:
        outcome_terms = inferred_outcomes

    parts: list[str] = []
    for terms in (
        condition_terms,
        intervention_terms,
        intent.population_terms,
        outcome_terms,
    ):
        if terms:
            parts.append("(" + " OR ".join(_quoted_title_abstract(term) for term in terms[:3]) + ")")
    if not parts:
        safe_tokens = _safe_keyword_tokens(question)
        if safe_tokens:
            parts.append(" AND ".join(_quoted_title_abstract(term) for term in safe_tokens[:5]))
        else:
            parts.append(question)
    if filters.recent_literature_only:
        current_year = datetime.now(timezone.utc).year
        parts.append(f'("{current_year - 5}"[Date - Publication] : "3000"[Date - Publication])')
    return " AND ".join(parts)


def _parse_abstracts(xml_text: str) -> dict[str, str]:
    root = ElementTree.fromstring(xml_text)
    abstracts: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID")
        if not pmid:
            continue
        chunks: list[str] = []
        for abstract in article.findall(".//Abstract/AbstractText"):
            label = abstract.attrib.get("Label")
            text = "".join(abstract.itertext()).strip()
            if not text:
                continue
            chunks.append(f"{label}: {text}" if label else text)
        abstracts[pmid] = " ".join(chunks)
    return abstracts


def _normalize_pubmed_record(
    pmid: str,
    summary: dict[str, Any],
    abstract_text: str,
    rank: int,
) -> NormalizedSource:
    title = (summary.get("title") or f"PubMed article {pmid}").rstrip(".")
    published_at = (summary.get("sortpubdate") or summary.get("pubdate") or "")[:10] or None
    authors = [
        author.get("name")
        for author in summary.get("authors", [])
        if author.get("name")
    ][:5]
    pubtypes = summary.get("pubtype", [])[:4]
    journal = summary.get("fulljournalname") or summary.get("source")
    metadata = {
        "journal": journal,
        "authors": authors,
        "publication_types": pubtypes,
    }

    snippets: list[EvidenceSnippet] = []
    title_text = compact_text(
        [
            title,
            f"Journal: {journal}." if journal else "",
            f"Published: {published_at}." if published_at else "",
        ]
    )
    snippets.append(
        EvidenceSnippet(
            snippet_id=f"pm_{stable_id(pmid, 'title', title_text[:180])}",
            source_type=SourceType.pubmed,
            source_id=pmid,
            identifier=f"PMID:{pmid}",
            title=title,
            section="title",
            text=title_text,
            source_rank=rank + 1,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            published_at=published_at,
        )
    )

    metadata_text = compact_text(
        [
            f"Publication types: {', '.join(pubtypes)}." if pubtypes else "",
            f"Authors: {', '.join(authors[:3])}." if authors else "",
        ]
    )
    if metadata_text:
        snippets.append(
            EvidenceSnippet(
                snippet_id=f"pm_{stable_id(pmid, 'metadata', metadata_text[:180])}",
                source_type=SourceType.pubmed,
                source_id=pmid,
                identifier=f"PMID:{pmid}",
                title=title,
                section="metadata",
                text=metadata_text,
                source_rank=rank + 1,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                published_at=published_at,
            )
        )

    for index, chunk in enumerate(split_sentences(abstract_text), start=1):
        snippets.append(
            EvidenceSnippet(
                snippet_id=f"pm_{stable_id(pmid, f'abstract_{index}', chunk[:180])}",
                source_type=SourceType.pubmed,
                source_id=pmid,
                identifier=f"PMID:{pmid}",
                title=title,
                section=f"abstract_{index}",
                text=chunk,
                source_rank=rank + 1,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                published_at=published_at,
            )
        )

    return NormalizedSource(
        source_type=SourceType.pubmed,
        source_id=pmid,
        identifier=f"PMID:{pmid}",
        title=title,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        published_at=published_at,
        metadata=metadata,
        raw_payload={"summary": summary, "abstract": abstract_text},
        snippets=snippets,
    )


class PubMedService:
    def __init__(self) -> None:
        self._throttle_lock = asyncio.Lock()

    async def _rate_limit(self) -> None:
        if settings.ncbi_api_key:
            return
        async with self._throttle_lock:
            await asyncio.sleep(0.34)

    def _base_params(self) -> dict[str, str]:
        params = {
            "tool": settings.ncbi_tool_name,
            "email": settings.ncbi_tool_email,
        }
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key
        return params

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    async def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._rate_limit()
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            trust_env=False,
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    async def _get_text(self, url: str, params: dict[str, Any]) -> str:
        await self._rate_limit()
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            trust_env=False,
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.text

    async def search(
        self,
        intent: QuestionIntent,
        question: str,
        filters: QAFilters,
        max_records: int,
    ) -> list[NormalizedSource]:
        term = build_search_term(intent, question, filters)
        search_params = {
            **self._base_params(),
            "db": "pubmed",
            "retmode": "json",
            "sort": "relevance",
            "retmax": min(max_records, 8),
            "term": term,
        }
        search_json = await self._get_json(settings.pubmed_search_url, search_params)
        ids = search_json.get("esearchresult", {}).get("idlist", [])[: max_records]
        if not ids:
            return []

        joined_ids = ",".join(ids)
        summary_json = await self._get_json(
            settings.pubmed_summary_url,
            {
                **self._base_params(),
                "db": "pubmed",
                "retmode": "json",
                "id": joined_ids,
            },
        )
        fetch_xml = await self._get_text(
            settings.pubmed_fetch_url,
            {
                **self._base_params(),
                "db": "pubmed",
                "retmode": "xml",
                "rettype": "abstract",
                "id": joined_ids,
            },
        )
        abstracts = _parse_abstracts(fetch_xml)
        result = summary_json.get("result", {})
        records: list[NormalizedSource] = []
        for rank, pmid in enumerate(ids):
            summary = result.get(pmid)
            if not summary:
                continue
            records.append(
                _normalize_pubmed_record(
                    pmid=pmid,
                    summary=summary,
                    abstract_text=abstracts.get(pmid, ""),
                    rank=rank,
                )
            )
        return records
