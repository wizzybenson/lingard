"""Curriculum graph nodes and edges (SPEC §8.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lingard_contracts.common import Language, Skill, node_language

NodeKind = Literal["cando", "function", "grammar", "lexset", "pron", "tasktype", "conj_cell"]
EdgeKind = Literal["requires", "exercises", "assessed_by", "prereq"]

KIND_SEGMENT: dict[str, str] = {
    "cando": "cando",
    "function": "func",
    "grammar": "grammar",
    "lexset": "lex",
    "pron": "pron",
    "tasktype": "task",
    "conj_cell": "conj",
}


class CurriculumNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^(fr|en)\.[a-z_]+(\.[a-z0-9_]+)+$")
    kind: NodeKind
    language: Language
    band: int = Field(ge=1, le=12)
    skill: Skill | None = None
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)
    source_url: str
    as_of: str
    version: int = 1
    reviewed: bool = False
    reviewed_by: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> CurriculumNode:
        if node_language(self.key) != self.language:
            raise ValueError(f"{self.key}: key prefix does not match language {self.language}")
        segment = self.key.split(".")[1]
        if segment != KIND_SEGMENT[self.kind]:
            raise ValueError(f"{self.key}: second segment must be {KIND_SEGMENT[self.kind]!r} for kind {self.kind}")
        return self


class CurriculumEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    from_key: str
    to_key: str
    kind: EdgeKind
