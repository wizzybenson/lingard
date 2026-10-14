"""Suite registry, results and gates."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results"
Mode = Literal["offline", "live"]


@dataclass
class Gate:
    metric: str
    op: Literal["<=", ">=", "=="]
    threshold: float

    def check(self, value: float) -> bool:
        return {"<=": value <= self.threshold, ">=": value >= self.threshold, "==": value == self.threshold}[self.op]


@dataclass
class SuiteResult:
    suite: str
    mode: Mode
    metrics: dict[str, float]
    gates: list[Gate]
    notes: list[str] = field(default_factory=list)
    samples: list[dict[str, object]] = field(default_factory=list)
    ran_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    @property
    def evaluated(self) -> bool:
        """At least one gate had data. A suite without gate data is INCOMPLETE, never a pass."""
        return any(g.metric in self.metrics for g in self.gates)

    @property
    def passed(self) -> bool:
        return self.evaluated and all(g.check(self.metrics[g.metric]) for g in self.gates if g.metric in self.metrics)

    @property
    def status(self) -> str:
        if not self.evaluated:
            return "INCOMPLETE"
        return "PASS" if self.passed else "FAIL"

    def failures(self) -> list[str]:
        return [
            f"{g.metric}={self.metrics.get(g.metric)} (needs {g.op} {g.threshold})"
            for g in self.gates
            if g.metric in self.metrics and not g.check(self.metrics[g.metric])
        ]

    def save(self) -> Path:
        RESULTS.mkdir(parents=True, exist_ok=True)
        path = RESULTS / f"{self.suite}.{self.mode}.json"
        payload = {**asdict(self), "status": self.status, "samples": self.samples[:50]}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
        return path


SuiteFn = Callable[[Mode], Awaitable[SuiteResult]]


@dataclass
class Suite:
    name: str
    run: SuiteFn
    watches: tuple[str, ...]
    """Repo path prefixes whose changes should re-run this suite (CI ``--changed-only``)."""
    live_only: bool = False


REGISTRY: dict[str, Suite] = {}


def suite(name: str, *, watches: tuple[str, ...], live_only: bool = False) -> Callable[[SuiteFn], SuiteFn]:
    def register(fn: SuiteFn) -> SuiteFn:
        REGISTRY[name] = Suite(name, fn, watches, live_only)
        return fn

    return register
