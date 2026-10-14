"""Deterministic scene contracts for evals, expanded from ``datasets/scenes.yaml``."""

from __future__ import annotations

from typing import Any

import yaml

from evals.framework import ROOT
from lingard_contracts.scene import SceneContract, npc_band_for
from lingard_world import load_city

AMOUNTS = [35, 60, 85, 120, 240, 375, 480, 650, 900, 1150]


def eval_scenes(count: int = 50) -> list[tuple[SceneContract, int, str]]:
    """(contract, learner_band, a number that appears in the approved facts)."""
    data: dict[str, list[dict[str, Any]]] = yaml.safe_load((ROOT / "evals/datasets/scenes.yaml").read_text())
    templates = [(city, t) for city, items in data.items() for t in items]
    scenes = []
    for i in range(count):
        city, template = templates[i % len(templates)]
        amount = AMOUNTS[(i // len(templates)) % len(AMOUNTS)]
        npc = load_city(ROOT / "content", city).npc(template["npc_key"])  # type: ignore[arg-type]
        targets = template["targets"]
        elicitation = [
            {
                "target": key,
                "tactic": f"Steer the talk so the newcomer naturally needs {key.split('.')[-1].replace('_', ' ')}",
            }
            for kind in ("functions", "grammar", "lexset")
            for key in targets.get(kind, [])
        ]
        contract = SceneContract.model_validate(
            {
                "city": city,
                "location_key": template["location_key"],
                "cast": [{"npc_key": npc.key, "role": npc.role, "voice_id": npc.voice_id}],
                "learner_goal": template["goal"],
                "targets": targets,
                "elicitation": elicitation,
                "approved_facts": [f.format(n=amount) for f in template["facts"]],
                "npc_language_band": npc_band_for(template["band"]),
                "accent_variety": [npc.accent],
                "success_conditions": ["The newcomer achieves the goal"],
                "evidence_required": [{"target": targets["grammar"][0], "min_uses": 1}],
                "max_turns": 16,
                "exits": [{"key": "done", "trigger": "goal reached or abandoned", "consequence": "scene ends"}],
            }
        )
        scenes.append((contract, int(template["band"]), str(amount)))
    return scenes
