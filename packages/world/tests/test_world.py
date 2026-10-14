from pathlib import Path

import pytest

from lingard_world import load_city

CONTENT = Path(__file__).resolve().parents[3] / "content"


@pytest.mark.parametrize("city", ["rivemont", "ashford"])
def test_city_content_is_valid_and_has_three_npcs_in_first_district(city: str) -> None:
    content = load_city(CONTENT, city)  # type: ignore[arg-type]
    first = min(content.city.districts, key=lambda d: d.order)
    npc_keys = {h.npc_key for loc in first.locations for h in loc.hotspots if h.kind == "npc"}
    assert len(npc_keys) == 3
    assert all(content.npc(k).world_facts for k in npc_keys)


def test_view_hides_locked_districts_and_places_npcs_by_hour() -> None:
    content = load_city(CONTENT, "rivemont")
    view = content.view(hour=12, band=5)
    by_key = {d.key: d for d in view.districts}
    assert by_key["rivemont.vieux_port"].unlocked
    assert not by_key["rivemont.saint_roch"].unlocked and by_key["rivemont.saint_roch"].locations == []
    martin = next(n for n in view.npcs if n.key == "landlord_martin")
    assert martin.location_key == "rivemont.vieux_port.cafe_quai"
    assert next(n for n in content.view(hour=22, band=5).npcs if n.key == "cafe_chloe").location_key is None
    assert content.view(hour=10, band=6).districts[1].unlocked


def test_ashford_mirrors_rivemont_structure() -> None:
    fr, en = load_city(CONTENT, "rivemont"), load_city(CONTENT, "ashford")
    assert [d.min_band for d in fr.city.districts] == [d.min_band for d in en.city.districts]
    assert len(fr.npcs) == len(en.npcs)
