"""Writing practice prompts (``content/packs/<pack>/writing_prompts.yaml``), each tagged with the task variant it
practises (a formal letter, a problem–solution essay), so every variant the exam sets is covered."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel


class WritingPrompt(BaseModel):
    prompt: str
    variant: str | None = None


@cache
def writing_prompts(content_root: Path, pack_id: str) -> dict[str, tuple[WritingPrompt, ...]]:
    """Prompts per writing task id. An entry is a plain string or ``{prompt, variant}``."""
    path = content_root / "packs" / pack_id / "writing_prompts.yaml"
    data = (yaml.safe_load(path.read_text()) if path.is_file() else None) or {}
    return {
        str(task): tuple(WritingPrompt.model_validate(e if isinstance(e, dict) else {"prompt": e}) for e in entries)
        for task, entries in data.items()
    }
