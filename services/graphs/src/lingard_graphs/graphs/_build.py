"""Small helpers for assembling graphs."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from typing import Any

from langgraph.graph import END, START, StateGraph


def linear(graph: StateGraph[Any, Any, Any, Any], steps: Sequence[tuple[str, Callable[..., Any]]]) -> None:
    """Add ``steps`` as nodes wired START → step₁ → … → stepₙ → END."""
    for name, fn in steps:
        graph.add_node(name, fn)
    graph.add_edge(START, steps[0][0])
    for (a, _), (b, _) in itertools.pairwise(steps):
        graph.add_edge(a, b)
    graph.add_edge(steps[-1][0], END)
