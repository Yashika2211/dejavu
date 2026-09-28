"""Runtime settings, read from the environment and the repo-root `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All tunables for DejaVu. Field names map 1:1 to upper-case env vars."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM (Groq, OpenAI-compatible)
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_primary: str = "openai/gpt-oss-120b"
    llm_fast: str = "openai/gpt-oss-20b"
    llm_fallbacks: Annotated[list[str], NoDecode] = ["qwen/qwen3.8-27b"]
    llm_reasoning_effort: Literal["low", "medium", "high"] = "medium"
    llm_max_context_tokens: int = 6000
    llm_rpm: int = 30
    llm_tpm: int = 8000
    llm_rpd: int = 1000
    llm_prices: dict[str, list[float]] = {}  # USD per 1M tokens: {"model": [input, output]}
    llm_timeout_s: float = 60.0

    # Hindsight
    hindsight_base_url: str = "https://api.hindsight.vectorize.io"
    hindsight_api_key: SecretStr | None = None
    dejavu_bank_live: str = "kestrel-ops-live"
    dejavu_bank_trained: str = "kestrel-ops-trained"
    dejavu_bank_day1: str = "kestrel-ops-day1"

    # App
    demo_mode: Literal["live", "replay"] = "live"
    sim_seed: int = 42
    api_port: int = 8000
    web_port: int = 3000
    http_timeout_s: float = 30.0

    @field_validator("llm_fallbacks", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("groq_api_key", "hindsight_api_key", mode="before")
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def configured_models(self) -> list[str]:
        """Every model the app may call, primary first, without duplicates."""
        return list(dict.fromkeys([self.llm_primary, self.llm_fast, *self.llm_fallbacks]))


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
