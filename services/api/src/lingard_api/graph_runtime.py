"""Interactive graphs (placement, Exam Hall) run in the API process, resumed through LangGraph interrupts.

Threads are named ``<kind>:<user_id>:<uuid>`` so ownership is checked on every resume.
"""

from __future__ import annotations

import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from lingard_exam_packs.items import ItemBank
from lingard_graphs.deps import GraphDeps
from lingard_graphs.graphs.exam_hall import build_exam_hall
from lingard_graphs.graphs.placement import build_placement

KINDS = ("placement", "exam")


class ThreadAccessError(PermissionError):
    pass


@dataclass
class Step:
    thread_id: str
    done: bool
    prompt: dict[str, Any] | None
    result: dict[str, Any] | None


def _step(thread_id: str, output: dict[str, Any]) -> Step:
    pending = output.get("__interrupt__")
    if pending:
        return Step(thread_id, False, dict(pending[0].value), None)
    keep = {k: v for k, v in output.items() if not k.startswith("_")}
    return Step(thread_id, True, None, keep)


class InteractiveGraphs:
    def __init__(self, deps: GraphDeps, bank: ItemBank, saver: BaseCheckpointSaver[str]) -> None:
        self.deps = deps
        self._graphs: dict[str, CompiledStateGraph[Any, Any, Any, Any]] = {
            "placement": build_placement(deps, bank, saver),
            "exam": build_exam_hall(deps, bank, saver),
        }

    async def start(self, kind: str, user_id: uuid.UUID, payload: dict[str, Any]) -> Step:
        thread_id = f"{kind}:{user_id}:{uuid.uuid4().hex}"
        output = await self._graphs[kind].ainvoke(
            {**payload, "user_id": user_id}, {"configurable": {"thread_id": thread_id}}
        )
        return _step(thread_id, output)

    async def resume(self, thread_id: str, user_id: uuid.UUID, value: Any) -> Step:
        kind, owner, *_ = [*thread_id.split(":"), "", ""]
        if kind not in KINDS or owner != str(user_id):
            raise ThreadAccessError("not your thread")
        output = await self._graphs[kind].ainvoke(Command(resume=value), {"configurable": {"thread_id": thread_id}})
        return _step(thread_id, output)


async def open_saver(stack: AsyncExitStack, database_url: str | None) -> BaseCheckpointSaver[str]:
    if database_url is None:
        return InMemorySaver()
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    saver = await stack.enter_async_context(
        AsyncPostgresSaver.from_conn_string(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    )
    await saver.setup()
    return saver
