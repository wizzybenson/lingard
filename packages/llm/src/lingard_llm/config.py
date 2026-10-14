"""Router configuration: tiers map to an ordered list of models (primary first, then fallbacks)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["fast", "mid", "frontier"]
Provider = Literal["anthropic", "openai", "scripted", "recorded"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


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
    timeout_s: float = Field(default=60, gt=0)
    price: Price | None = None


class TierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    models: list[ModelSpec] = Field(min_length=1)
    retries: int = Field(default=1, ge=0, le=5)


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tiers: dict[Tier, TierConfig]
    fixtures_dir: str = "evals/fixtures/llm"

    @classmethod
    def load(cls, path: str | Path) -> LLMConfig:
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))

    def tier(self, tier: Tier) -> TierConfig:
        try:
            return self.tiers[tier]
        except KeyError as exc:
            raise KeyError(f"tier {tier!r} is not configured") from exc
