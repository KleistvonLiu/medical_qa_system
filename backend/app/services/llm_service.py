from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Sequence, TypeVar

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlmodel import Session

from ..config import Settings, settings
from ..schemas import QAAnswerDraft, QAFilters, QuestionIntent
from .cache import get_embedding, set_embedding
from .text_utils import content_hash


SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(frozen=True)
class ProviderRuntime:
    name: str
    base_url: str | None = None
    api_key: str | None = None
    chat_model: str | None = None
    embedding_model: str | None = None
    enable_thinking: bool = True
    strip_think_output: bool = False

    @property
    def chat_configured(self) -> bool:
        if self.name == "none":
            return False
        if self.name == "openai":
            return bool(self.api_key and self.chat_model)
        return bool(self.base_url and self.chat_model)

    @property
    def embedding_configured(self) -> bool:
        if self.name == "none":
            return False
        if self.name == "openai":
            return bool(self.api_key and self.embedding_model)
        return bool(self.base_url and self.embedding_model)

    @property
    def client_api_key(self) -> str:
        if self.name == "vllm":
            return self.api_key or "dummy"
        return self.api_key or ""

    @property
    def embedding_cache_key(self) -> str | None:
        if not self.embedding_model:
            return None
        return f"{self.name}:{self.embedding_model}"


class LLMService:
    def __init__(self, runtime_settings: Settings = settings) -> None:
        self.settings = runtime_settings
        self.chat_runtime = self._build_chat_runtime()
        self.embedding_runtime = self._build_embedding_runtime()
        self.chat_client = self._build_client(self.chat_runtime) if self.chat_runtime.chat_configured else None
        self.embedding_client = (
            self._build_client(self.embedding_runtime)
            if self.embedding_runtime.embedding_configured
            else None
        )

    @property
    def configured(self) -> bool:
        return self.chat_configured

    @property
    def chat_configured(self) -> bool:
        return self.chat_client is not None

    @property
    def embedding_configured(self) -> bool:
        return self.embedding_client is not None

    @property
    def chat_provider_name(self) -> str:
        return self.chat_runtime.name

    @property
    def embedding_provider_name(self) -> str:
        return self.embedding_runtime.name

    @property
    def embeddings_enabled(self) -> bool:
        return self.embedding_configured

    def debug_status(self) -> dict[str, Any]:
        return {
            "chat_provider": self.chat_provider_name,
            "embedding_provider": self.embedding_provider_name,
            "chat_configured": self.chat_configured,
            "embedding_configured": self.embedding_configured,
            "embeddings_enabled": self.embeddings_enabled,
        }

    async def aclose(self) -> None:
        clients: list[AsyncOpenAI] = []
        if self.chat_client is not None:
            clients.append(self.chat_client)
        if self.embedding_client is not None and self.embedding_client is not self.chat_client:
            clients.append(self.embedding_client)
        for client in clients:
            await client.close()

    async def extract_intent(self, question: str, filters: QAFilters) -> QuestionIntent:
        if not self.chat_client:
            return self._heuristic_intent(question, filters)

        try:
            prompt = (
                "Classify the clinical question for a retrieval system grounded in "
                "ClinicalTrials.gov and PubMed. Return a small, conservative search plan. "
                "Prefer route='trials' for recruiting or eligibility questions, route='pubmed' "
                "for published evidence questions, and route='blended' when both are needed."
            )
            parsed = await self._parse_structured_chat_completion(
                schema_name="question_intent",
                schema_model=QuestionIntent,
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "filters": filters.model_dump(),
                            }
                        ),
                    },
                ],
            )
            parsed.filters = QAFilters(
                recruiting_only=filters.recruiting_only or parsed.filters.recruiting_only,
                recent_literature_only=(
                    filters.recent_literature_only or parsed.filters.recent_literature_only
                ),
            )
            return parsed
        except Exception:
            return self._heuristic_intent(question, filters)

    async def compose_answer(
        self,
        question: str,
        intent: QuestionIntent,
        snippets: Sequence[dict[str, Any]],
        retry_invalid: bool = False,
    ) -> QAAnswerDraft:
        if not self.chat_client:
            raise RuntimeError("Chat provider is not configured")

        constraint_line = (
            "Use only snippet_ids from the provided evidence."
            if retry_invalid
            else "Return citation_ids that support the answer."
        )
        prompt = (
            "You write conservative, evidence-grounded clinical QA summaries. "
            "Use only the evidence provided. Separate trial evidence from published "
            "literature when relevant. Do not give personalized medical advice. "
            "Return 2-4 concise why_this_answer bullets and 1-3 concise limitations bullets. "
            "Do not leave why_this_answer or limitations empty. "
            "When the question asks about recruiting or ongoing trials, explicitly mention the "
            "trial identifiers and statuses that support the answer. "
            "When the route is blended, include both trial and published literature evidence if available. "
            f"{constraint_line}"
        )
        return await self._parse_structured_chat_completion(
            schema_name="qa_answer",
            schema_model=QAAnswerDraft,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": question,
                            "intent": intent.model_dump(mode="json"),
                            "evidence": list(snippets),
                        }
                    ),
                },
            ],
        )

    async def embed_texts(
        self,
        session: Session,
        texts: Sequence[str],
    ) -> list[list[float]] | None:
        if not self.embedding_client or not texts:
            return None

        cache_model = self.embedding_runtime.embedding_cache_key
        if not cache_model or not self.embedding_runtime.embedding_model:
            return None

        cached: list[list[float] | None] = []
        misses: list[str] = []
        miss_positions: list[int] = []
        for index, text in enumerate(texts):
            text_hash = content_hash(text)
            found = get_embedding(session, cache_model, text_hash)
            cached.append(found)
            if found is None:
                misses.append(text)
                miss_positions.append(index)

        if misses:
            response = await self.embedding_client.embeddings.create(
                model=self.embedding_runtime.embedding_model,
                input=list(misses),
            )
            for position, item, original_text in zip(
                miss_positions,
                response.data,
                misses,
                strict=True,
            ):
                embedding = list(item.embedding)
                cached[position] = embedding
                set_embedding(
                    session,
                    cache_model,
                    content_hash(original_text),
                    embedding,
                )

        return [embedding or [] for embedding in cached]

    def _build_chat_runtime(self) -> ProviderRuntime:
        provider = self.settings.resolved_chat_provider
        if provider == "openai":
            return ProviderRuntime(
                name="openai",
                base_url=self.settings.openai_base_url,
                api_key=self.settings.openai_api_key,
                chat_model=self.settings.resolved_openai_chat_model,
                enable_thinking=True,
                strip_think_output=False,
            )
        if provider == "vllm":
            return ProviderRuntime(
                name="vllm",
                base_url=self.settings.vllm_base_url,
                api_key=self.settings.vllm_api_key,
                chat_model=self.settings.vllm_chat_model,
                enable_thinking=self.settings.vllm_enable_thinking,
                strip_think_output=self.settings.vllm_strip_think_output,
            )
        return ProviderRuntime(name="none")

    def _build_embedding_runtime(self) -> ProviderRuntime:
        provider = self.settings.resolved_embed_provider
        if provider == "openai":
            return ProviderRuntime(
                name="openai",
                base_url=self.settings.openai_base_url,
                api_key=self.settings.openai_api_key,
                embedding_model=self.settings.openai_embed_model,
            )
        if provider == "vllm":
            return ProviderRuntime(
                name="vllm",
                base_url=self.settings.vllm_base_url,
                api_key=self.settings.vllm_api_key,
                embedding_model=self.settings.vllm_embed_model,
            )
        return ProviderRuntime(name="none")

    def _build_client(self, runtime: ProviderRuntime) -> AsyncOpenAI | None:
        if runtime.name == "none":
            return None
        http_client = None
        if runtime.name == "vllm":
            http_client = httpx.AsyncClient(trust_env=False)
        return AsyncOpenAI(
            api_key=runtime.client_api_key,
            base_url=runtime.base_url,
            http_client=http_client,
        )

    async def _parse_structured_chat_completion(
        self,
        schema_name: str,
        schema_model: type[SchemaT],
        messages: list[dict[str, str]],
    ) -> SchemaT:
        if not self.chat_client or not self.chat_runtime.chat_model:
            raise RuntimeError("Chat provider is not configured")

        request_kwargs: dict[str, Any] = {
            "model": self.chat_runtime.chat_model,
            "messages": messages,
            "temperature": self.settings.chat_temperature,
            "max_tokens": self.settings.chat_max_completion_tokens,
            "response_format": self._chat_response_format(schema_name, schema_model),
        }
        if self.chat_runtime.name == "vllm" and not self.chat_runtime.enable_thinking:
            request_kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": False},
            }

        response = await self.chat_client.chat.completions.create(**request_kwargs)
        raw_content = self._extract_message_content(response)
        cleaned = self._normalize_structured_content(raw_content)
        return schema_model.model_validate_json(cleaned)

    def _chat_response_format(
        self,
        schema_name: str,
        schema_model: type[BaseModel],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema_model.model_json_schema(),
            },
        }
        if self.chat_runtime.name == "openai":
            payload["json_schema"]["strict"] = True
        return payload

    def _extract_message_content(self, response: Any) -> str:
        message = response.choices[0].message
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        text_parts.append(str(text))
                else:
                    text = getattr(item, "text", None)
                    if text:
                        text_parts.append(str(text))
            if text_parts:
                return "\n".join(text_parts)
        refusal = getattr(message, "refusal", None)
        if refusal:
            raise RuntimeError(f"Model refused structured output: {refusal}")
        raise RuntimeError("Chat provider returned no message content")

    def _normalize_structured_content(self, content: str) -> str:
        cleaned = content.strip()
        if self.chat_runtime.strip_think_output:
            cleaned = strip_think_blocks(cleaned)
        cleaned = cleaned.strip()
        if cleaned.startswith("{") and cleaned.endswith("}"):
            return cleaned

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return cleaned[start : end + 1]
        return cleaned

    def _heuristic_intent(self, question: str, filters: QAFilters) -> QuestionIntent:
        lowered = question.lower()
        trials_keywords = {"recruit", "eligib", "enroll", "trial", "study site"}
        pubmed_keywords = {
            "published",
            "literature",
            "paper",
            "review",
            "evidence",
            "safety",
            "efficacy",
            "effectiveness",
        }
        route = "blended"
        if any(keyword in lowered for keyword in trials_keywords) and not any(
            keyword in lowered for keyword in pubmed_keywords
        ):
            route = "trials"
        elif any(keyword in lowered for keyword in pubmed_keywords) and not any(
            keyword in lowered for keyword in trials_keywords
        ):
            route = "pubmed"
        focus = "overview"
        if "safety" in lowered or "adverse" in lowered:
            focus = "safety"
        elif "efficacy" in lowered or "effective" in lowered:
            focus = "efficacy"
        elif "recruit" in lowered:
            focus = "recruiting"
        return QuestionIntent(
            route=route,
            focus=focus,
            condition_terms=[],
            intervention_terms=[],
            population_terms=[],
            outcome_terms=[],
            filters=filters,
        )


def strip_think_blocks(text: str) -> str:
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    prefix_pattern = re.compile(
        r"^\s*(thinking process|thought process|reasoning|思考过程|推理过程)\s*:",
        re.IGNORECASE,
    )
    if not prefix_pattern.match(cleaned):
        return cleaned

    first_json = cleaned.find("{")
    if first_json != -1:
        return cleaned[first_json:].strip()

    marker = re.search(r"\n\s*\n", cleaned)
    if marker:
        return cleaned[marker.end() :].strip()
    return cleaned
