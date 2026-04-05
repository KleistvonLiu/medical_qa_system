from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.schemas import QAFilters, RetrievalRoute
from app.services.llm_service import LLMService


ENV_KEYS = [
    "CHAT_PROVIDER",
    "EMBED_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_CHAT_MODEL",
    "OPENAI_MODEL",
    "OPENAI_EMBED_MODEL",
    "VLLM_BASE_URL",
    "VLLM_API_KEY",
    "VLLM_CHAT_MODEL",
    "VLLM_EMBED_MODEL",
    "VLLM_ENABLE_THINKING",
    "VLLM_STRIP_THINK_OUTPUT",
    "SQLITE_PATH",
]


def clear_provider_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class FakeChatCompletions:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=self.content,
                        refusal=None,
                    )
                )
            ]
        )


class FakeEmbeddings:
    def __init__(self):
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0, 0.0]) for _ in kwargs["input"]])


class FakeClient:
    def __init__(self, content: str):
        self.chat = SimpleNamespace(completions=FakeChatCompletions(content))
        self.embeddings = FakeEmbeddings()


def test_settings_preserve_legacy_openai_defaults(monkeypatch):
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-legacy")

    configured = Settings(_env_file=None)

    assert configured.resolved_chat_provider == "openai"
    assert configured.resolved_embed_provider == "openai"
    assert configured.resolved_openai_chat_model == "gpt-legacy"


def test_settings_default_vllm_to_no_embeddings(monkeypatch):
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("CHAT_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_CHAT_MODEL", "qwen35")

    configured = Settings(_env_file=None)

    assert configured.resolved_chat_provider == "vllm"
    assert configured.resolved_embed_provider == "none"


def test_settings_require_explicit_vllm_embedding_model(monkeypatch):
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("CHAT_PROVIDER", "vllm")
    monkeypatch.setenv("EMBED_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_CHAT_MODEL", "qwen35")

    service = LLMService(Settings(_env_file=None))

    assert service.embedding_provider_name == "vllm"
    assert service.embedding_configured is False


def test_sqlite_path_is_resolved_relative_to_backend_dir(monkeypatch):
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("SQLITE_PATH", "clinical_qa.db")

    configured = Settings(_env_file=None)

    assert configured.database_url.endswith("/backend/clinical_qa.db")


def test_settings_model_config_uses_backend_env_file():
    env_file = Settings.model_config.get("env_file")
    assert str(env_file).endswith("/backend/.env")


@pytest.mark.asyncio
async def test_openai_structured_intent_uses_chat_completions_json_schema(monkeypatch):
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-5-mini")

    fake_client = FakeClient(
        '{"route":"pubmed","focus":"safety","condition_terms":[],"intervention_terms":[],"population_terms":[],"outcome_terms":[],"filters":{"recruiting_only":false,"recent_literature_only":false}}'
    )
    monkeypatch.setattr(LLMService, "_build_client", lambda self, runtime: fake_client)

    service = LLMService(Settings(_env_file=None))
    intent = await service.extract_intent(
        "What does the literature say about semaglutide safety?",
        QAFilters(),
    )

    assert intent.route == RetrievalRoute.pubmed
    request = fake_client.chat.completions.calls[0]
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["name"] == "question_intent"
    assert request["response_format"]["json_schema"]["strict"] is True


@pytest.mark.asyncio
async def test_vllm_structured_intent_disables_thinking_and_strips_noise(monkeypatch):
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("CHAT_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_CHAT_MODEL", "qwen35")
    monkeypatch.setenv("VLLM_ENABLE_THINKING", "false")
    monkeypatch.setenv("VLLM_STRIP_THINK_OUTPUT", "true")

    fake_client = FakeClient(
        '<think>reasoning</think>\n{"route":"trials","focus":"recruiting","condition_terms":[],"intervention_terms":[],"population_terms":[],"outcome_terms":[],"filters":{"recruiting_only":false,"recent_literature_only":false}}'
    )
    monkeypatch.setattr(LLMService, "_build_client", lambda self, runtime: fake_client)

    service = LLMService(Settings(_env_file=None))
    intent = await service.extract_intent(
        "Are there any recruiting clinical trials for pembrolizumab?",
        QAFilters(),
    )

    assert intent.route == RetrievalRoute.trials
    request = fake_client.chat.completions.calls[0]
    assert request["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
