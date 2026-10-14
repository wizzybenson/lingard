"""Simulated CRS (SPEC §18.1) from the official grid in ``content/crs/crs_grid.yaml``.

Labelled everywhere as simulated, for motivation; not an official assessment.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

DISCLAIMER = "Simulated score for motivation only — not an official assessment."
Education = Literal[
    "less_than_secondary",
    "secondary",
    "one_year_post_secondary",
    "two_year_post_secondary",
    "bachelors",
    "two_or_more",
    "masters",
    "phd",
]
SKILLS = ("listening", "reading", "writing", "speaking")


class CrsInputs(BaseModel):
    """Non-language factors the learner enters once (``learner_profiles.crs_inputs``)."""

    model_config = ConfigDict(extra="forbid")

    age: int = Field(ge=16, le=80)
    education: Education
    canadian_work_years: int = Field(default=0, ge=0)
    foreign_work_years: int = Field(default=0, ge=0)
    has_spouse_coming: bool = False
    spouse_education: Education | None = None
    spouse_canadian_work_years: int = 0
    spouse_language_clb: dict[str, int] | None = None
    certificate_of_qualification: bool = False
    sibling_in_canada: bool = False
    canadian_education_years: int = 0
    provincial_nomination: bool = False


class LanguageLevels(BaseModel):
    """CLB per skill for the first official language, and optionally the second (NCLC values on the CLB scale)."""

    first: dict[str, int]
    first_is_french: bool
    second: dict[str, int] | None = None


class CrsBreakdown(BaseModel):
    core: dict[str, int]
    spouse: dict[str, int]
    transferability: dict[str, int]
    additional: dict[str, int]
    total: int
    disclaimer: str = DISCLAIMER


@cache
def load_grid(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return data


def _ladder(levels: list[dict[str, Any]], clb: int, column: int | None) -> int:
    for step in levels:
        if clb >= step["min_clb"]:
            points = step["points"]
            return int(points[column] if column is not None else points)
    return 0


def _years(table: dict[Any, Any], years: int) -> Any:
    return table[min(years, max(int(k) for k in table))]


def compute(inputs: CrsInputs, languages: LanguageLevels, grid_path: Path) -> CrsBreakdown:
    grid = load_grid(grid_path)
    col = 0 if inputs.has_spouse_coming else 1
    first = {s: languages.first.get(s, 0) for s in SKILLS}
    second = {s: (languages.second or {}).get(s, 0) for s in SKILLS}

    core = {
        "age": int(grid["age"].get(inputs.age, [0, 0])[col]),
        "education": int(grid["education"][inputs.education][col]),
        "first_language": sum(_ladder(grid["first_language_per_ability"], first[s], col) for s in SKILLS),
        "second_language": min(
            sum(_ladder(grid["second_language_per_ability"], second[s], col) for s in SKILLS),
            int(grid["second_language_cap"][col]),
        ),
        "canadian_work": int(_years(grid["canadian_work_years"], inputs.canadian_work_years)[col]),
    }

    spouse = {"education": 0, "language": 0, "canadian_work": 0}
    if inputs.has_spouse_coming:
        sp = grid["spouse"]
        spouse["education"] = int(sp["education"][inputs.spouse_education or "less_than_secondary"])
        spouse["language"] = sum(
            _ladder(sp["language_per_ability"], (inputs.spouse_language_clb or {}).get(s, 0), None) for s in SKILLS
        )
        spouse["canadian_work"] = int(_years(sp["canadian_work_years"], inputs.spouse_canadian_work_years))

    tr = grid["transferability"]
    tier = int(tr["education_tier"][inputs.education])
    min_first = min(first.values())
    language_tier = 1 if min_first >= 9 else (0 if min_first >= 7 else None)

    def pair(table: dict[str, list[int]], key: str | None, column: int | None) -> int:
        return 0 if key is None or column is None else int(table[key][column])

    edu_key = None if tier == 0 else f"tier{tier}"
    canada_col = None if inputs.canadian_work_years < 1 else (0 if inputs.canadian_work_years == 1 else 1)
    foreign_key = (
        None if inputs.foreign_work_years < 1 else ("one_to_two" if inputs.foreign_work_years < 3 else "three_plus")
    )
    education_group = min(
        pair(tr["education_language"], edu_key, language_tier)
        + pair(tr["education_canadian_work"], edu_key, canada_col),
        tr["pair_cap"],
    )
    foreign_group = min(
        pair(tr["foreign_work_language"], foreign_key, language_tier)
        + pair(tr["foreign_work_canadian_work"], foreign_key, canada_col),
        tr["pair_cap"],
    )
    certificate = 0
    if inputs.certificate_of_qualification:
        if min_first >= 7:
            certificate = tr["certificate_language"]["clb7_all"]
        elif min_first >= 5:
            certificate = tr["certificate_language"]["clb5_some_under7"]
    transferability = {"education": education_group, "foreign_work": foreign_group, "certificate": certificate}
    transfer_total = min(sum(transferability.values()), tr["cap"])
    transferability["capped_total"] = transfer_total

    add = grid["additional"]
    french = languages.second if not languages.first_is_french else languages.first
    english = languages.first if not languages.first_is_french else languages.second
    french_bonus = 0
    if french and min(french.get(s, 0) for s in SKILLS) >= 7:
        english_all_5 = bool(english) and min((english or {}).get(s, 0) for s in SKILLS) >= 5
        french_bonus = (
            add["french_nclc7_english_clb5_plus"] if english_all_5 else add["french_nclc7_english_clb4_or_less"]
        )
    canadian_education = 0
    if inputs.canadian_education_years >= 3:
        canadian_education = add["canadian_education_three_plus_years"]
    elif inputs.canadian_education_years >= 1:
        canadian_education = add["canadian_education_one_two_years"]
    additional = {
        "sibling": add["sibling"] if inputs.sibling_in_canada else 0,
        "french": french_bonus,
        "canadian_education": canadian_education,
        "provincial_nomination": add["provincial_nomination"] if inputs.provincial_nomination else 0,
    }
    additional_total = min(sum(additional.values()), add["cap"])
    total = sum(core.values()) + sum(spouse.values()) + transfer_total + additional_total
    return CrsBreakdown(core=core, spouse=spouse, transferability=transferability, additional=additional, total=total)
