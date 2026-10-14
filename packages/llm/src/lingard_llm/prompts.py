"""Versioned prompt files: ``prompts/<name>/v<N>.md``. Every LLM call carries name and version."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

_VERSION_FILE = re.compile(r"^v(\d+)\.md$")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    template: str

    @property
    def ref(self) -> str:
        return f"{self.name}@v{self.version}"

    def render(self, **values: object) -> str:
        """``$name`` placeholders; a missing value is an error, never a silent blank."""
        return Template(self.template).substitute({k: str(v) for k, v in values.items()})


class PromptRegistry:
    def __init__(self, root: str | Path, pins: dict[str, int] | None = None) -> None:
        self._root = Path(root)
        self._pins = pins or {}
        self._cache: dict[tuple[str, int], Prompt] = {}

    def versions(self, name: str) -> list[int]:
        folder = self._root / name
        if not folder.is_dir():
            raise KeyError(f"no prompt named {name!r} under {self._root}")
        found = [int(m.group(1)) for p in folder.iterdir() if (m := _VERSION_FILE.match(p.name))]
        if not found:
            raise KeyError(f"prompt {name!r} has no versions")
        return sorted(found)

    def get(self, name: str, version: int | None = None) -> Prompt:
        chosen = version or self._pins.get(name) or self.versions(name)[-1]
        key = (name, chosen)
        if key not in self._cache:
            path = self._root / name / f"v{chosen}.md"
            if not path.is_file():
                raise KeyError(f"prompt {name}@v{chosen} not found")
            self._cache[key] = Prompt(name=name, version=chosen, template=path.read_text())
        return self._cache[key]
