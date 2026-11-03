"""Application configuration, loaded from environment variables / `.env`."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for TriageOps.

    Every value can be overridden with an environment variable of the same
    (case-insensitive) name. A local `.env` file is loaded automatically.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core ──────────────────────────────────────────────────────────────
    app_name: str = "TriageOps"
    environment: str = "development"
    database_url: str = "sqlite:///./triageops.db"
    log_level: str = "INFO"
    cors_origins: str = ""

    # ── Triage policy ─────────────────────────────────────────────────────
    budget_threshold: float = Field(default=5_000.0, gt=0)
    min_description_chars: int = Field(default=60, ge=20, le=2_000)
    triage_provider: Literal["auto", "rules", "openai", "gemini"] = "auto"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: float = Field(default=12.0, ge=1, le=60)

    # ── Demo helpers ──────────────────────────────────────────────────────
    seed_demo_data: bool = True
    enable_demo_tools: bool = True

    @field_validator("openai_api_key", "gemini_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def effective_provider(self) -> str:
        """Resolve ``auto`` into the concrete provider that will be used."""
        if self.triage_provider == "auto":
            if self.openai_api_key:
                return "openai"
            if self.gemini_api_key:
                return "gemini"
            return "rules"
        return self.triage_provider


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
