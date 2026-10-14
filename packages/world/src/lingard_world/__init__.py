"""Renderer-independent world: city content, NPC schedules, district unlocks (SPEC §19.1)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from lingard_contracts.common import CityKey
from lingard_contracts.world import City, DistrictView, Location, NpcPersona, NpcView, WorldView


@dataclass(frozen=True)
class CityContent:
    city: City
    npcs: dict[str, NpcPersona]

    def location(self, key: str) -> Location:
        for district in self.city.districts:
            for location in district.locations:
                if location.key == key:
                    return location
        raise KeyError(f"{self.city.key} has no location {key!r}")

    def npc(self, key: str) -> NpcPersona:
        try:
            return self.npcs[key]
        except KeyError as exc:
            raise KeyError(f"{self.city.key} has no NPC {key!r}") from exc

    def unlocked_districts(self, band: int, extra: list[str] | None = None) -> list[str]:
        unlocked = {d.key for d in self.city.districts if d.min_band <= band}
        return sorted(
            unlocked | set(extra or []), key=lambda k: next(d.order for d in self.city.districts if d.key == k)
        )

    def view(self, hour: int, band: int, extra_unlocks: list[str] | None = None) -> WorldView:
        unlocked = set(self.unlocked_districts(band, extra_unlocks))
        return WorldView(
            city=self.city.key,
            name=self.city.name,
            hour=hour,
            districts=[
                DistrictView(
                    key=d.key,
                    name=d.name,
                    unlocked=d.key in unlocked,
                    min_band=d.min_band,
                    locations=d.locations if d.key in unlocked else [],
                )
                for d in sorted(self.city.districts, key=lambda d: d.order)
            ],
            npcs=[
                NpcView(key=n.key, name=n.name, role=n.role, location_key=n.location_at(hour))
                for n in self.npcs.values()
            ],
        )


def validate(content: CityContent) -> list[str]:
    """Referential checks: hotspots point at real NPCs, schedules at real locations, keys are city-prefixed."""
    problems = []
    locations = {loc.key for d in content.city.districts for loc in d.locations}
    for district in content.city.districts:
        if not district.key.startswith(f"{content.city.key}."):
            problems.append(f"district {district.key} lacks city prefix")
        for location in district.locations:
            if not location.key.startswith(f"{district.key}."):
                problems.append(f"location {location.key} not under {district.key}")
            for hotspot in location.hotspots:
                if hotspot.kind == "npc" and hotspot.npc_key not in content.npcs:
                    problems.append(f"hotspot {hotspot.key} references unknown NPC {hotspot.npc_key}")
    for npc in content.npcs.values():
        if npc.city != content.city.key:
            problems.append(f"NPC {npc.key} belongs to {npc.city}")
        for slot in npc.schedule:
            if slot.location_key not in locations:
                problems.append(f"NPC {npc.key} scheduled at unknown location {slot.location_key}")
            if slot.from_hour >= slot.to_hour:
                problems.append(f"NPC {npc.key} has an empty schedule slot")
        if not npc.accent.startswith(content.city.language):
            problems.append(f"NPC {npc.key} accent {npc.accent} does not match city language")
    return problems


@cache
def load_city(content_root: Path, key: CityKey) -> CityContent:
    folder = content_root / "cities" / key
    city = City.model_validate(yaml.safe_load((folder / "city.yaml").read_text()))
    raw_npcs = yaml.safe_load((folder / "npcs.yaml").read_text())["npcs"]
    npcs = {n["key"]: NpcPersona.model_validate(n) for n in raw_npcs}
    content = CityContent(city=city, npcs=npcs)
    problems = validate(content)
    if problems:
        raise ValueError(f"{key} content invalid: {problems}")
    return content
