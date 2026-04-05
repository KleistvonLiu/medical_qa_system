from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings
from ..schemas import EvidenceSnippet, NormalizedSource, QAFilters, QuestionIntent, SourceType
from .text_utils import compact_text, stable_id, tokenize


logger = logging.getLogger(__name__)
GENERIC_QUERY_TOKENS = {
    "are",
    "there",
    "any",
    "clinical",
    "trial",
    "trials",
    "study",
    "studies",
    "recruiting",
    "recruit",
    "enrolling",
    "enroll",
    "published",
    "literature",
    "what",
    "does",
    "say",
    "about",
    "ongoing",
    "already",
    "exists",
    "exist",
    "evidence",
}

RECRUITING_STATUSES = {"RECRUITING"}
ONGOING_STATUSES = {
    "RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "NOT_YET_RECRUITING",
    "ENROLLING_BY_INVITATION",
}

FOLLOW_UP_CLAUSE = re.compile(
    r"\s+and\s+(what\s+)?(published\s+)?(evidence|literature|results?)\b.*$",
    re.IGNORECASE,
)


def _nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def build_search_params(intent: QuestionIntent, question: str, limit: int) -> dict[str, Any]:
    params: dict[str, Any] = {"pageSize": min(limit, 8)}

    condition_terms = [term.strip() for term in intent.condition_terms if term.strip()]
    intervention_terms = [term.strip() for term in intent.intervention_terms if term.strip()]
    inferred_intervention, inferred_condition = infer_terms_from_question(question)

    if not condition_terms and inferred_condition:
        condition_terms = [inferred_condition]
    if not intervention_terms and inferred_intervention:
        intervention_terms = [inferred_intervention]

    if condition_terms:
        params["query.cond"] = " OR ".join(condition_terms[:3])
    if intervention_terms:
        params["query.intr"] = " OR ".join(intervention_terms[:3])

    fallback_query = build_safe_query_term(
        " ".join(intent.outcome_terms[:2]) or " ".join(intent.population_terms[:2]) or question
    )
    if not params.get("query.cond") and not params.get("query.intr") and fallback_query:
        params["query.term"] = fallback_query
    return params


def build_fallback_search_params(question: str, limit: int) -> dict[str, Any]:
    params: dict[str, Any] = {"pageSize": min(limit, 8)}
    inferred_intervention, inferred_condition = infer_terms_from_question(question)
    if inferred_condition:
        params["query.cond"] = inferred_condition
    if inferred_intervention:
        params["query.intr"] = inferred_intervention
    safe_query = build_safe_query_term(question)
    if safe_query and not (inferred_condition or inferred_intervention):
        params["query.term"] = safe_query
    elif safe_query and (inferred_condition or inferred_intervention):
        params["query.term"] = safe_query
    return params


def infer_desired_statuses(question: str, filters: QAFilters) -> set[str] | None:
    lowered = question.lower()
    if filters.recruiting_only or "recruit" in lowered or "enroll" in lowered:
        return RECRUITING_STATUSES
    if "ongoing" in lowered or "active" in lowered:
        return ONGOING_STATUSES
    return None


def build_search_plan(
    intent: QuestionIntent,
    question: str,
    filters: QAFilters,
    limit: int,
) -> tuple[list[dict[str, Any]], set[str] | None]:
    desired_statuses = infer_desired_statuses(question, filters)
    fetch_limit = max(limit, 20) if desired_statuses else limit
    param_candidates = [
        build_search_params(intent, question, fetch_limit),
        build_fallback_search_params(question, fetch_limit),
    ]
    for params in param_candidates:
        params["pageSize"] = fetch_limit
    if desired_statuses == RECRUITING_STATUSES:
        for params in param_candidates:
            params["filter.overallStatus"] = "RECRUITING"
    return param_candidates, desired_statuses


def build_safe_query_term(text: str) -> str:
    tokens = [token for token in tokenize(text) if token not in GENERIC_QUERY_TOKENS]
    compact = " ".join(tokens[:8]).strip()
    return compact


def _strip_follow_up_clause(text: str) -> str:
    return FOLLOW_UP_CLAUSE.sub("", text).strip(" ,.;:")


def infer_terms_from_question(question: str) -> tuple[str | None, str | None]:
    normalized = re.sub(r"\s+", " ", question.strip().rstrip("?")).lower()
    match = re.search(r"\bfor\s+(.+?)\s+in\s+(.+)$", normalized)
    if not match:
        return None, None

    intervention = _strip_follow_up_clause(match.group(1).strip(" ,.;:"))
    condition = _strip_follow_up_clause(match.group(2).strip(" ,.;:"))
    intervention = build_safe_query_term(intervention)
    condition = build_safe_query_term(condition)
    return intervention or None, condition or None


def is_recruiting(status: str | None) -> bool:
    if not status:
        return False
    return "recruit" in status.lower()


def normalize_study(study: dict[str, Any], rank: int) -> NormalizedSource | None:
    protocol = study.get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    description = protocol.get("descriptionModule", {})
    conditions_mod = protocol.get("conditionsModule", {})
    arms_mod = protocol.get("armsInterventionsModule", {})
    eligibility = protocol.get("eligibilityModule", {})
    design = protocol.get("designModule", {})
    outcomes = protocol.get("outcomesModule", {})
    locations_mod = protocol.get("contactsLocationsModule", {})
    sponsor_mod = protocol.get("sponsorCollaboratorsModule", {})

    nct_id = ident.get("nctId")
    title = ident.get("briefTitle") or ident.get("officialTitle")
    if not nct_id or not title:
        return None

    phases = design.get("phases") or []
    conditions = conditions_mod.get("conditions") or []
    interventions = [
        item.get("name")
        for item in arms_mod.get("interventions", [])
        if item.get("name")
    ]
    locations = [
        compact_text(
            [
                location.get("facility"),
                location.get("city"),
                location.get("country"),
            ],
            separator=", ",
        )
        for location in locations_mod.get("locations", [])
    ]
    locations = [location for location in locations if location]
    primary_outcomes = [
        compact_text([item.get("measure"), item.get("timeFrame")], separator=" - ")
        for item in outcomes.get("primaryOutcomes", [])
    ]
    primary_outcomes = [item for item in primary_outcomes if item]

    status_text = compact_text(
        [
            f"Status: {status.get('overallStatus')}.",
            f"Study type: {design.get('studyType')}." if design.get("studyType") else "",
            f"Phase: {', '.join(phases)}." if phases else "",
            f"Conditions: {', '.join(conditions[:4])}." if conditions else "",
            f"Interventions: {', '.join(interventions[:4])}." if interventions else "",
        ]
    )
    summary_text = description.get("briefSummary") or description.get("detailedDescription")
    eligibility_text = compact_text(
        [
            f"Sex: {eligibility.get('sex')}." if eligibility.get("sex") else "",
            f"Ages: {', '.join(eligibility.get('stdAges', []))}."
            if eligibility.get("stdAges")
            else "",
            f"Minimum age: {eligibility.get('minimumAge')}."
            if eligibility.get("minimumAge")
            else "",
            f"Maximum age: {eligibility.get('maximumAge')}."
            if eligibility.get("maximumAge")
            else "",
            eligibility.get("eligibilityCriteria") or "",
        ]
    )
    outcome_text = (
        "Primary outcomes: " + "; ".join(primary_outcomes[:4])
        if primary_outcomes
        else ""
    )

    snippets: list[EvidenceSnippet] = []
    for section, text in (
        ("status", status_text),
        ("summary", summary_text or ""),
        ("eligibility", eligibility_text),
        ("outcomes", outcome_text),
    ):
        if not text:
            continue
        snippet_id = f"ct_{stable_id(nct_id, section, text[:180])}"
        snippets.append(
            EvidenceSnippet(
                snippet_id=snippet_id,
                source_type=SourceType.clinical_trials,
                source_id=nct_id,
                identifier=nct_id,
                title=title,
                section=section,
                text=text.strip(),
                source_rank=rank + 1,
                url=f"https://clinicaltrials.gov/study/{nct_id}",
                published_at=_nested(status, "lastUpdatePostDateStruct", "date"),
            )
        )

    metadata = {
        "overall_status": status.get("overallStatus"),
        "study_type": design.get("studyType"),
        "phases": phases,
        "conditions": conditions,
        "interventions": interventions,
        "lead_sponsor": _nested(sponsor_mod, "leadSponsor", "name"),
        "locations": locations[:6],
        "primary_outcomes": primary_outcomes[:6],
    }
    return NormalizedSource(
        source_type=SourceType.clinical_trials,
        source_id=nct_id,
        identifier=nct_id,
        title=title,
        url=f"https://clinicaltrials.gov/study/{nct_id}",
        published_at=_nested(status, "lastUpdatePostDateStruct", "date"),
        metadata=metadata,
        raw_payload=study,
        snippets=snippets,
    )


class ClinicalTrialsService:
    def __init__(self) -> None:
        self.base_url = settings.clinical_trials_base_url

    def _build_headers(self) -> dict[str, str]:
        tool = settings.ncbi_tool_name.strip() if settings.ncbi_tool_name else "clinical-qa-mvp"
        email = settings.ncbi_tool_email.strip() if settings.ncbi_tool_email else "demo@example.com"
        return {
            "Accept": "application/json",
            "User-Agent": f"{tool}/0.1 ({email})",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    async def _fetch(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"{self.base_url}/studies?{urlencode(params, doseq=True)}"

        def _request() -> dict[str, Any]:
            request = Request(url, headers=self._build_headers())
            with urlopen(request, timeout=settings.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))

        return await asyncio.to_thread(_request)

    async def search(
        self,
        intent: QuestionIntent,
        question: str,
        filters: QAFilters,
        max_records: int,
    ) -> list[NormalizedSource]:
        param_candidates, desired_statuses = build_search_plan(
            intent,
            question,
            filters,
            max_records,
        )

        seen_keys: set[tuple[tuple[str, Any], ...]] = set()
        for params in param_candidates:
            cache_key = tuple(sorted(params.items()))
            if cache_key in seen_keys:
                continue
            seen_keys.add(cache_key)
            try:
                payload = await self._fetch(params)
            except (HTTPError, URLError, TimeoutError, ValueError) as error:
                logger.warning("clinicaltrials_fetch_failed params=%s error=%s", params, error)
                continue

            studies = payload.get("studies", [])
            results: list[NormalizedSource] = []
            for rank, study in enumerate(studies):
                normalized = normalize_study(study, rank)
                if normalized is None:
                    continue
                status = str(normalized.metadata.get("overall_status") or "")
                if desired_statuses and status not in desired_statuses:
                    continue
                results.append(normalized)
                if len(results) >= max_records:
                    break
            if results or studies:
                return results
        return []
