"""``writing_review`` graph (SPEC §11): submission → 3 scored samples → aggregate → rewrite → tags → evidence."""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict

from lingard_contracts.assessment import WritingAssessment
from lingard_contracts.common import PackId, Skill
from lingard_graphs.agents.writing import WritingExaminer
from lingard_graphs.deps import GraphDeps
from lingard_graphs.graphs._build import linear
from lingard_graphs.pedagogy.bands import observe, prior
from lingard_graphs.pedagogy.mastery import MasteryState, apply_evidence
from lingard_graphs.pedagogy.tickets import Example, record_error


class WritingState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: uuid.UUID
    pack: PackId
    task_id: str
    task_prompt: str
    text: str
    trace_id: str | None = None
    assessment: WritingAssessment | None = None
    submission_id: uuid.UUID | None = None


def build_writing_review(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver[str] | None = None
) -> CompiledStateGraph[WritingState, Any, WritingState, WritingState]:
    examiner = WritingExaminer(deps.router, deps.prompts, deps.content_root)
    rules = deps.pedagogy

    async def score_x3(state: WritingState) -> dict[str, Any]:
        pack = deps.packs.pack(state.pack)
        task = next(t for t in pack.section_for(Skill.WRITING).tasks if t.id == state.task_id)
        nodes = await deps.nodes_for(pack.language, max_band=12)
        result = await examiner.score(
            pack=pack,
            conversion=deps.packs.conversion(state.pack),
            task=task,
            task_prompt=state.task_prompt,
            response=state.text,
            nodes=nodes,
            trace_id=state.trace_id,
        )
        return {"assessment": result}

    async def aggregate(state: WritingState) -> dict[str, Any]:
        """Median-of-three already applied per criterion; this node records the submission."""
        assert state.assessment is not None
        submission_id = await deps.store.save_writing(state.user_id, state.task_prompt, state.text, state.assessment)
        return {"submission_id": submission_id}

    async def rewrite(state: WritingState) -> dict[str, Any]:
        assert state.assessment is not None
        if not state.assessment.rewrite.strip():
            return {"assessment": state.assessment.model_copy(update={"rewrite": state.text})}
        return {}

    async def tag_errors(state: WritingState) -> dict[str, Any]:
        """Only tags confirmed by ≥ 2 of 3 independent samples are showable; the rest stay evidence."""
        return {}

    async def update_evidence(state: WritingState) -> dict[str, Any]:
        assert state.assessment is not None
        pack = deps.packs.pack(state.pack)
        posteriors = await deps.store.posteriors(state.user_id)
        posterior = posteriors.get((state.pack, "writing")) or prior(pack, Skill.WRITING, None, rules.bands)
        posterior = observe(posterior, pack, Skill.WRITING, state.assessment.band_or_points, "writing", rules.bands)
        await deps.store.save_posterior(state.user_id, state.pack, "writing", posterior)
        now = deps.clock()
        keys = sorted({t.node_key for t in state.assessment.error_tags})
        mastery = await deps.store.mastery(state.user_id, keys)
        tickets = await deps.store.tickets(state.user_id, active_only=False)
        context = f"writing:{state.submission_id}"
        for tag in state.assessment.error_tags:
            m = mastery.setdefault(tag.node_key, MasteryState(tag.node_key, rules.bkt.p_init))
            apply_evidence(m, False, confidence=tag.confidence, difficulty=0.7, context=context, params=rules.bkt)
            errors = await deps.store.recent_errors(state.user_id, tag.node_key)
            await deps.store.record_error_time(state.user_id, tag.node_key, now)
            ticket, _ = record_error(
                tickets.get(tag.node_key),
                tag.node_key,
                Example(now, tag.span.text, context),
                0.8 if tag.severity != "minor" else 0.5,
                errors,
                rules.tickets,
            )
            if ticket is not None:
                tickets[tag.node_key] = ticket
                await deps.store.save_ticket(state.user_id, ticket)
        await deps.store.save_mastery(state.user_id, list(mastery.values()), now)
        return {}

    graph = StateGraph(WritingState)
    steps = [
        ("score_x3", score_x3),
        ("aggregate", aggregate),
        ("rewrite", rewrite),
        ("tag_errors", tag_errors),
        ("update_evidence", update_evidence),
    ]
    linear(graph, steps)
    return graph.compile(checkpointer=checkpointer)
