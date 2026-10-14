"""Graph worker settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class GraphSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://lingard:lingard@localhost:55432/lingard"
    redis_url: str = "redis://localhost:56379/0"
    content_root: Path = REPO_ROOT / "content"
    prompts_root: Path = REPO_ROOT / "prompts"
    llm_config: Path = REPO_ROOT / "config" / "llm.yaml"
    max_attempts: int = 4
