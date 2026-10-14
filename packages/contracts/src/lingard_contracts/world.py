"""Renderer-independent world model (SPEC §19.1). Content YAML validates against these."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from lingard_contracts.common import CityKey, Language, Locale, Strict


class Hotspot(Strict):
    key: str
    kind: Literal["npc", "object", "sign", "door"]
    label: str
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    npc_key: str | None = None
    text: str | None = None


class Location(Strict):
    key: str
    name: str
    description: str
    layer_art: list[str] = Field(default_factory=list)
    hotspots: list[Hotspot] = Field(default_factory=list)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)


class District(Strict):
    key: str
    name: str
    min_band: int = Field(ge=1, le=12)
    order: int
    description: str
    locations: list[Location] = Field(min_length=1)


class City(Strict):
    key: CityKey
    name: str
    language: Language
    locale: Locale
    country: str
    school: str
    """Name of the city's language school (Teacher + School, SPEC §12)."""
    districts: list[District] = Field(min_length=1)


class ScheduleSlot(Strict):
    from_hour: int = Field(ge=0, le=23)
    to_hour: int = Field(ge=1, le=24)
    location_key: str


class NpcPersona(Strict):
    key: str
    city: CityKey
    name: str
    role: str
    age: int
    personality: str
    backstory: str
    speech_style: str
    secret: str = ""
    world_facts: list[str] = Field(default_factory=list)
    voice_id: str
    accent: str
    schedule: list[ScheduleSlot] = Field(min_length=1)

    def location_at(self, hour: int) -> str | None:
        for slot in self.schedule:
            if slot.from_hour <= hour < slot.to_hour:
                return slot.location_key
        return None


class NpcView(Strict):
    key: str
    name: str
    role: str
    location_key: str | None


class DistrictView(Strict):
    key: str
    name: str
    unlocked: bool
    min_band: int
    locations: list[Location]


class WorldView(Strict):
    """What ``GET /v1/world/{city}`` returns; the client only renders it."""

    city: CityKey
    name: str
    hour: int
    districts: list[DistrictView]
    npcs: list[NpcView]
