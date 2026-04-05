from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_name: str = "Clinical QA MVP"
    app_env: str = "development"
    api_prefix: str = "/api"
    frontend_origin: str = "http://localhost:5173"

    chat_provider: str | None = None
    embed_provider: str | None = None

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str | None = None
    openai_model: str | None = None
    openai_embed_model: str = "text-embedding-3-small"

    vllm_base_url: str = "http://127.0.0.1:8000/v1"
    vllm_api_key: str | None = None
    vllm_chat_model: str | None = None
    vllm_embed_model: str | None = None
    vllm_enable_thinking: bool = False
    vllm_strip_think_output: bool = True

    chat_max_completion_tokens: int = Field(default=700, ge=64, le=4096)
    chat_temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    ncbi_tool_name: str = "clinical-qa-mvp"
    ncbi_tool_email: str = "demo@example.com"
    ncbi_api_key: str | None = None

    sqlite_path: str = "clinical_qa.db"

    query_cache_ttl_hours: int = 6
    clinical_trials_ttl_hours: int = 24
    pubmed_ttl_hours: int = 24 * 7
    max_sources_default: int = Field(default=6, ge=1, le=8)
    rerank_candidate_limit: int = 16

    clinical_trials_base_url: str = "https://clinicaltrials.gov/api/v2"
    pubmed_search_url: str = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    )
    pubmed_summary_url: str = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    )
    pubmed_fetch_url: str = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    )

    request_timeout_seconds: float = 20.0

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        resolved = Path(self.sqlite_path).expanduser()
        if not resolved.is_absolute():
            resolved = (BACKEND_DIR / resolved).resolve()
        return f"sqlite:///{resolved}"

    @property
    def resolved_chat_provider(self) -> str:
        return self._normalize_provider(self.chat_provider or "openai")

    @property
    def resolved_embed_provider(self) -> str:
        if self.embed_provider:
            return self._normalize_provider(self.embed_provider)
        if self.resolved_chat_provider == "vllm":
            return "none"
        return "openai"

    @property
    def resolved_openai_chat_model(self) -> str:
        return self.openai_chat_model or self.openai_model or "gpt-5-mini"

    @staticmethod
    def _normalize_provider(value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"openai", "vllm", "none"}:
            raise ValueError(f"Unsupported provider: {value}")
        return normalized


settings = Settings()
