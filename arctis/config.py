"""Application configuration (environment-driven)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loaded from environment variables (and optional ``.env``)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(
        default="sqlite+pysqlite:///./arctis_dev.db",
        alias="DATABASE_URL",
        description="SQLAlchemy database URL (sync driver).",
    )
    allowed_origins: str = Field(
        default=(
            "http://localhost:3000,"
            "http://127.0.0.1:3000,"
            "http://localhost:5173,"
            "http://127.0.0.1:5173"
        ),
        alias="ALLOWED_ORIGINS",
        description="Comma-separated CORS origins.",
    )
    env: Literal["dev", "prod"] = Field(default="dev", alias="ENV")
    #: When set, overrides auto rule: ``1``/``on``/``true`` = expose; ``0``/``off`` = hide.
    arctis_expose_openapi: str | None = Field(default=None, alias="ARCTIS_EXPOSE_OPENAPI")
    #: **Unsafe.** Only with ``ENV=dev``: if DB is down, accept any non-empty ``X-API-Key`` and use
    #: :attr:`dbless_dev_tenant_id`. Never enable in production.
    unsafe_allow_dbless_dev_auth: bool = Field(default=False, alias="ARCTIS_UNSAFE_ALLOW_DBLESS_DEV_AUTH")
    dbless_dev_tenant_id: str = Field(
        default="00000000-0000-0000-0000-000000000001",
        alias="ARCTIS_DBLESS_DEV_TENANT_ID",
    )
    #: When no rate-limit row exists: if set to ``>0``, use as per-minute cap; ``0`` = no synthetic cap.
    #: If unset: **prod** uses 120/min, **dev** has no synthetic cap.
    arctis_default_rate_limit_per_minute: int | None = Field(
        default=None,
        alias="ARCTIS_DEFAULT_RATE_LIMIT_PER_MINUTE",
    )
    #: **Dev only.** If true with ``ENV=dev``, CORS allows all origins (``*``). Never use in prod.
    cors_wildcard_dev: bool = Field(default=False, alias="ARCTIS_CORS_WILDCARD_DEV")

    # Observability
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")

    # Default LLM (when tenant has no stored LLM key)
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="deepseek-r1:7b", alias="OLLAMA_MODEL")
    use_ollama_when_no_tenant_key: bool = Field(
        default=False,
        alias="ARCTIS_USE_OLLAMA",
        description="If true and no tenant LLM key, use local Ollama (no API key).",
    )
    governance_cross_tenant_queries: bool = Field(
        default=False,
        alias="ARCTIS_GOVERNANCE_CROSS_TENANT",
        description="If true, metrics/audit export may use tenant_id different from API key tenant.",
    )
    audit_jsonl_export_dir: str | None = Field(
        default=None,
        alias="ARCTIS_AUDIT_JSONL_DIR",
        description="Directory of JSONL files from JsonlFileAuditSink for GET /audit/export.",
    )
    audit_store: Literal["jsonl", "db", "none"] = Field(
        default="jsonl",
        alias="ARCTIS_AUDIT_STORE",
        description="Audit query backend: jsonl directory, DB table, or disabled.",
    )
    budget_max_tokens_per_run: int | None = Field(
        default=None,
        alias="ARCTIS_BUDGET_MAX_TOKENS_PER_RUN",
        description="Hard cap on estimated tokens per run (E2); unset = no per-run cap.",
    )
    e6_cost_prices_json: str | None = Field(
        default=None,
        alias="ARCTIS_E6_COST_PRICES_JSON",
        description='Optional JSON map of model → {"prompt": EUR/1k, "completion": EUR/1k} for E6.',
    )

    def openapi_docs_exposed(self) -> bool:
        """Whether ``/docs``, ``/redoc``, ``/openapi.json`` are mounted and listed as public paths."""
        raw = self.arctis_expose_openapi
        if raw is not None and str(raw).strip():
            return str(raw).strip().lower() in ("1", "true", "yes", "on")
        return self.env == "dev"

    def synthetic_rate_limit_per_minute(self) -> int | None:
        """
        Per-minute ceiling when **no** ``TenantRateLimitRecord`` / ``ApiKeyRateLimitRecord`` exists.
        """
        raw = self.arctis_default_rate_limit_per_minute
        if raw is not None:
            if raw <= 0:
                return None
            return int(raw)
        if self.env == "prod":
            return 120
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
