from pathlib import Path

import yaml

from tools.content_cli.art import ROOT, build


def test_every_location_has_both_art_layers() -> None:
    for city_file in (ROOT / "content" / "cities").glob("*/city.yaml"):
        for district in yaml.safe_load(city_file.read_text())["districts"]:
            for location in district["locations"]:
                assert len(location["layer_art"]) == 2, location["key"]
                for layer in location["layer_art"]:
                    assert (ROOT / "content" / "art" / layer).is_file(), layer


def test_committed_art_matches_the_generator(tmp_path: Path) -> None:
    (tmp_path / "cities").symlink_to(ROOT / "content" / "cities")
    for path in build(tmp_path):
        committed = ROOT / "content" / path.relative_to(tmp_path)
        assert committed.read_text() == path.read_text(), f"{committed} is stale: run python -m tools.content_cli.art"
