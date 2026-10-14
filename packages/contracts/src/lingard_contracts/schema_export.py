"""Export JSON Schemas for the TypeScript client (``python -m lingard_contracts.schema_export <out_dir>``)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from lingard_contracts.assessment import BandEstimate, ErrorTag, UtteranceAssessment, WritingAssessment
from lingard_contracts.events import TurnEvent
from lingard_contracts.planning import DayPlan, Lesson
from lingard_contracts.scene import SceneContract
from lingard_contracts.world import NpcPersona, WorldView

EXPORTED: tuple[type[BaseModel], ...] = (
    TurnEvent,
    SceneContract,
    UtteranceAssessment,
    WritingAssessment,
    ErrorTag,
    BandEstimate,
    DayPlan,
    Lesson,
    WorldView,
    NpcPersona,
)


def export(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for model in EXPORTED:
        path = out_dir / f"{model.__name__}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(mode="serialization"), indent=2, sort_keys=True) + "\n")
        written.append(path)
    return written


def combined() -> dict[str, object]:
    """One schema whose ``$defs`` hold every exported model, so shared types are emitted once (TS generation)."""
    _, schema = models_json_schema([(m, "serialization") for m in EXPORTED], title="LingardContracts")
    defs = schema.get("$defs", {})
    schema["type"] = "object"
    schema["properties"] = {m.__name__: {"$ref": f"#/$defs/{m.__name__}"} for m in EXPORTED if m.__name__ in defs}
    return schema


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "schema")
    if "--combined" in sys.argv:
        target.write_text(json.dumps(combined(), indent=2, sort_keys=True) + "\n")
    else:
        export(target)
