"""Router configuration: tiers map to an ordered list of models (primary first, then fallbacks)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["fast", "guard", "mid", "frontier"]
Provider = Literal["anthropic", "openai", "google", "scripted", "recorded"]

PROVIDER_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}
"""The environment variable that switches each hosted provider on. Offline providers need none."""
Effort = Literal["low", "medium", "high", "xhigh", "max"]


def provider_configured(provider: str) -> bool:
    """True when the provider can be called: its API key is set, or it is an offline provider."""
    variable = PROVIDER_ENV.get(provider)
    return variable is None or bool(os.environ.get(variable, "").strip())


def any_llm_configured() -> bool:
    return any(provider_configured(p) for p in PROVIDER_ENV)


class Price(BaseModel):
    """USD per million tokens, with provenance (SPEC §0.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float = Field(default=0, ge=0)
    source_url: str
    as_of: str


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    model: str
    max_tokens: int = Field(default=4096, gt=0)
    effort: Effort | None = None
    thinking: bool = True
    """False turns a model's own reasoning off where the provider allows it (short, latency-critical answers)."""
    timeout_s: float = Field(default=60, gt=0)
    price: Price | None = None


class TierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    models: list[ModelSpec] = Field(min_length=1)
    retries: int = Field(default=1, ge=0, le=5)


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    price: Price | None = None


class TierDefaults(BaseModel):
    """One tier in ``config/llm.yaml``: catalog model names in preference order plus per-call settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    models: list[str] = Field(min_length=1)
    effort: Effort | None = None
    thinking: bool = True
    max_tokens: int = Field(default=4096, gt=0)
    timeout_s: float = Field(default=60, gt=0)
    retries: int = Field(default=1, ge=0, le=5)


class ConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog: dict[str, CatalogEntry]
    tiers: dict[Tier, TierDefaults]


def tier_override(tier: str, setting: str, env: Mapping[str, str]) -> str | None:
    """``LLM_<TIER>_<SETTING>`` from the environment, or ``None`` when unset or blank."""
    return env.get(f"LLM_{tier.upper()}_{setting}", "").strip() or None


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tiers: dict[Tier, TierConfig]
    fixtures_dir: str = "evals/fixtures/llm"

    @classmethod
    def load(cls, path: str | Path, env: Mapping[str, str] | None = None) -> LLMConfig:
        """Reads the catalog and tier defaults; ``LLM_<TIER>_MODELS`` (comma-separated), ``LLM_<TIER>_EFFORT`` and
        ``LLM_<TIER>_THINKING`` in ``env`` (default: the process environment) override a tier's settings."""
        env = os.environ if env is None else env
        file = ConfigFile.model_validate(yaml.safe_load(Path(path).read_text()))
        tiers: dict[Tier, TierConfig] = {}
        for tier, defaults in file.tiers.items():
            names = tier_override(tier, "MODELS", env)
            models = [n.strip() for n in names.split(",") if n.strip()] if names else defaults.models
            unknown = [n for n in models if n not in file.catalog]
            if unknown:
                raise ValueError(
                    f"LLM tier {tier!r} names models missing from the catalog in {path}: {', '.join(unknown)} "
                    f"(known: {', '.join(file.catalog)})"
                )
            effort = tier_override(tier, "EFFORT", env) or defaults.effort
            thinking_env = tier_override(tier, "THINKING", env)
            thinking = defaults.thinking if thinking_env is None else thinking_env.lower() in {"1", "true", "on"}
            specs = [
                {
                    "provider": file.catalog[name].provider,
                    "model": name,
                    "price": file.catalog[name].price,
                    "effort": effort,
                    "thinking": thinking,
                    "max_tokens": defaults.max_tokens,
                    "timeout_s": defaults.timeout_s,
                }
                for name in models
            ]
            tiers[tier] = TierConfig.model_validate({"models": specs, "retries": defaults.retries})
        return cls(tiers=tiers)

    def tier(self, tier: Tier) -> TierConfig:
        try:
            return self.tiers[tier]
        except KeyError as exc:
            raise KeyError(f"tier {tier!r} is not configured") from exc
