"""Typed settings (SPEC §24). Thresholds live here or in config/*.yaml, never inline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = Field(default="local", pattern="^(local|test|staging|prod)$")
    database_url: str = "postgresql+psycopg://lingard:lingard@localhost:55432/lingard"
    database_schema: str | None = None
    redis_url: str | None = "redis://localhost:56379/0"
    content_root: Path = REPO_ROOT / "content"
    config_root: Path = REPO_ROOT / "config"
    prompts_root: Path = REPO_ROOT / "prompts"
    object_store_url: str | None = None
    object_store_key: str = "lingard"
    object_store_secret: SecretStr = SecretStr("lingard-local-only")
    voicebox_url: str | None = None
    pronunciation_url: str | None = None
    """Internal pronunciation service (``lingard_pronunciation.server``); unset → Studio scoring unavailable."""
    elevenlabs_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    deepgram_api_key: SecretStr | None = None
    audio_retention_days: int = 30

    jwt_secret: SecretStr = SecretStr("local-dev-only-change-me-0123456789abcdef")
    jwt_issuer: str = "lingard"
    access_token_minutes: int = 15
    refresh_token_days: int = 60
    plan_reuse_minutes: int = 10
    """Starting a day while one is still being planned for the same city returns that plan (up to this age)."""
    world_hour: int = 12
    """The in-world hour the map shows (who is where). The story follows the learner's progress, not the real clock."""
    pin_reverify_days: int = 30

    argon2_time_cost: int = 3
    argon2_memory_kib: int = 65_536
    argon2_parallelism: int = 2

    lockout_after_failures: int = 5
    lockout_minutes: list[int] = [1, 5, 30]
    """Successive lockout durations; after the last one an admin reset is required (SPEC §23.2)."""
    rate_limit_per_ip_per_minute: int = 20
    rate_limit_per_name_per_minute: int = 10

    invite_days: int = 14
    livekit_url: str = "ws://localhost:57880"
    livekit_public_url: str = "ws://localhost:57880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: SecretStr = SecretStr("secret")
    cors_origins: list[str] = ["http://localhost:8081", "http://localhost:19006"]
    """The web app's origins. It must be same-site with the API so the SameSite=Strict refresh cookie is sent."""
    refresh_cookie_secure: bool | None = None
    """``Secure`` flag on the web refresh cookie; unset → on everywhere except local/test (plain http)."""

    @property
    def refresh_cookie_is_secure(self) -> bool:
        if self.refresh_cookie_secure is not None:
            return self.refresh_cookie_secure
        return self.env not in ("local", "test")

    def prod_safe(self) -> None:
        if self.env in ("staging", "prod") and self.jwt_secret.get_secret_value().startswith("local-dev-only"):
            raise RuntimeError("JWT_SECRET must be set outside local/test")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.prod_safe()
    return settings
