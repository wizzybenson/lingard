"""Location artwork (``python -m tools.content_cli.art``): original layered SVG scenes for every location.

Each location's ``layer_art`` names two files: ``*_bg.svg`` (room or street) and ``*_mid.svg`` (furniture and props,
drawn over it). Scenes are drawn from a template per kind of place, coloured with the city's palette, and signed
with the location's own name, so the same template reads differently in Rivemont and Ashford. Output is
deterministic: rerunning reproduces the files byte for byte.
"""

from __future__ import annotations

import random
import re
import sys
from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
W, H = 800, 500

KINDS: dict[str, str] = {
    "apartment": "home",
    "flat": "home",
    "cafe": "cafe",
    "bank": "bank",
    "emploi": "office",
    "job_centre": "office",
    "clinique": "clinic",
    "surgery": "clinic",
    "quincaillerie": "shop",
    "hardware": "shop",
    "hotel_de_ville": "hall",
    "town_hall": "hall",
    "bibliotheque": "library",
    "library": "library",
    "echo": "newsroom",
    "gazette": "newsroom",
}


def shade(colour: str, factor: float) -> str:
    """Lighten (factor > 1) or darken (< 1) a #rrggbb colour."""
    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    if factor >= 1:
        r, g, b = (round(c + (255 - c) * (factor - 1)) for c in (r, g, b))
    else:
        r, g, b = (round(c * factor) for c in (r, g, b))
    return f"#{min(r, 255):02x}{min(g, 255):02x}{min(b, 255):02x}"


def svg(body: str, defs: str = "") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"><defs>{defs}</defs>{body}</svg>\n'


def rect(x: float, y: float, w: float, h: float, fill: str, extra: str = "") -> str:
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" fill="{fill}" {extra}/>'


def text(x: float, y: float, value: str, size: int, fill: str, anchor: str = "middle", weight: str = "600") -> str:
    return (
        f'<text x="{x:g}" y="{y:g}" font-family="Helvetica, Arial, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def gradient(name: str, top: str, bottom: str) -> str:
    return (
        f'<linearGradient id="{name}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>'
    )


class Palette:
    def __init__(self, data: dict[str, object]) -> None:
        sky = data["sky"]
        assert isinstance(sky, list)
        self.sky_top, self.sky_bottom = str(sky[0]), str(sky[1])
        self.far, self.mid, self.near, self.water = (str(data[k]) for k in ("far", "mid", "near", "water"))


def interior(p: Palette, wall: str, floor: str, window_count: int = 2, rng: random.Random | None = None) -> str:
    """Back wall, skirting, floorboards and windows looking out on the city."""
    rng = rng or random.Random(0)  # noqa: S311 (art layout, not security)
    parts = [
        rect(0, 0, W, 360, "url(#wall)"),
        rect(0, 352, W, 10, shade(wall, 0.7)),
        rect(0, 360, W, 140, "url(#floor)"),
    ]
    for i in range(9):
        parts.append(f'<line x1="{i * 100}" y1="360" x2="{i * 100 - 60}" y2="500" stroke="{shade(floor, 0.8)}"/>')
    gap = W / (window_count + 1)
    for i in range(1, window_count + 1):
        x = gap * i - 70
        parts.append(rect(x - 8, 62, 156, 196, shade(wall, 0.75), 'rx="4"'))
        parts.append(rect(x, 70, 140, 180, "url(#sky)"))
        for b in range(5):  # skyline through the window
            bh = 40 + rng.randint(0, 70)
            parts.append(rect(x + b * 28, 250 - bh, 26, bh, p.far, 'opacity="0.8"'))
        parts.append(rect(x + 68, 70, 4, 180, shade(wall, 0.75)))
        parts.append(rect(x, 156, 140, 4, shade(wall, 0.75)))
    return "".join(parts)


def interior_defs(p: Palette, wall: str, floor: str) -> str:
    return (
        gradient("wall", shade(wall, 1.08), shade(wall, 0.92))
        + gradient("floor", shade(floor, 1.05), shade(floor, 0.8))
        + gradient("sky", p.sky_top, p.sky_bottom)
    )


def street(p: Palette, facade: str, rng: random.Random) -> str:
    """Sky, a far skyline and the pavement in front of a building."""
    parts = [rect(0, 0, W, H, "url(#sky)")]
    x = 0
    while x < W:
        bw, bh = 60 + rng.randint(0, 60), 120 + rng.randint(0, 120)
        parts.append(rect(x, 380 - bh, bw, bh, p.far, 'opacity="0.75"'))
        x += bw + 4
    parts += [rect(0, 380, W, 120, shade(p.mid, 0.85)), rect(0, 380, W, 8, shade(p.mid, 0.6))]
    return "".join(parts)


def fitted(x: float, y: float, value: str, width: float, largest: int, fill: str) -> str:
    """Centred label shrunk until it fits ``width`` (≈ 0.6 em per character in a sans-serif face)."""
    size = max(7, min(largest, int(width / (0.6 * max(len(value), 1)))))
    return text(x, y, value, size, fill)


def sign(x: float, y: float, w: float, label: str, board: str, ink: str) -> str:
    size = 22 if len(label) <= 24 else 17 if len(label) <= 34 else 14
    return rect(x, y, w, 40, board, 'rx="6"') + text(x + w / 2, y + 27, label, size, ink)


def hotspot(location: Location, *keys: str) -> dict[str, Any] | None:
    spots = {h["key"]: h for h in location.get("hotspots", [])}
    return next((spots[k] for k in keys if k in spots), None)


PRICE = re.compile(r"(\d+(?:[.,]\d+)?\s?\$|£\d+(?:\.\d+)?)")


# ── Scenes: (background, foreground) per kind ────────────────────────────────────────────────────────────────────
Location = dict[str, Any]
Scene = Callable[[Palette, Location, random.Random], tuple[str, str]]


def home(p: Palette, location: Location, rng: random.Random) -> tuple[str, str]:
    wall, floor = shade(p.sky_top, 0.97), shade(p.mid, 1.1)
    defect = ""
    if hotspot(location, "crack"):
        defect = f'<path d="M520 120 L548 175 L536 230" stroke="{shade(wall, 0.55)}" stroke-width="3" fill="none"/>'
    elif hotspot(location, "damp"):
        defect = f'<ellipse cx="560" cy="110" rx="46" ry="32" fill="{shade(wall, 0.72)}" opacity="0.8"/>'
        defect += f'<ellipse cx="548" cy="104" rx="26" ry="16" fill="{shade(wall, 0.6)}" opacity="0.7"/>'
    lease = hotspot(location, "lease", "tenancy")
    bg = svg(
        interior(p, wall, floor, 1, rng)
        + defect
        + rect(80, 110, 120, 90, shade(p.near, 1.4), 'rx="3"')
        + rect(90, 120, 100, 70, shade(p.sky_bottom, 1.1)),
        interior_defs(p, wall, floor),
    )
    sofa = shade(p.water, 1.15)
    fg = svg(
        rect(470, 300, 260, 90, sofa, 'rx="18"')
        + rect(450, 280, 40, 120, shade(sofa, 0.85), 'rx="14"')
        + rect(710, 280, 40, 120, shade(sofa, 0.85), 'rx="14"')
        + rect(500, 270, 200, 50, shade(sofa, 1.1), 'rx="14"')
        + rect(120, 330, 180, 14, shade(p.near, 1.2))
        + rect(130, 344, 10, 60, shade(p.near, 1.0))
        + rect(280, 344, 10, 60, shade(p.near, 1.0))
        + rect(150, 300, 110, 30, "#ffffff", 'rx="3" opacity="0.9"')
        + fitted(205, 319, (lease["label"] if lease else "").upper(), 100, 11, p.near)
        + f'<ellipse cx="600" cy="460" rx="220" ry="26" fill="{shade(p.mid, 0.9)}" opacity="0.5"/>'
    )
    return bg, fg


def cafe(p: Palette, location: Location, rng: random.Random) -> tuple[str, str]:
    name = location["name"]
    wall, floor = shade(p.mid, 1.35), shade(p.near, 1.3)
    shelves = "".join(
        rect(470 + i * 46, 120 + row * 50, 30, 36, [p.water, p.far, shade(p.mid, 0.8)][(i + row) % 3], 'rx="4"')
        for row in range(2)
        for i in range(6)
    )
    bg = svg(
        interior(p, wall, floor, 1, rng)
        + rect(450, 100, 310, 8, shade(p.near, 1.1))
        + rect(450, 150, 310, 8, shade(p.near, 1.1))
        + shelves
        + sign(450, 40, 310, name, shade(p.near, 0.9), "#fdf6e9")
        + rect(80, 290, 150, 50, "#2f2f2f", 'rx="4"')
        + text(155, 320, "MENU", 16, "#f4f4f4"),
        interior_defs(p, wall, floor),
    )
    fg = svg(
        rect(400, 300, 400, 120, shade(p.near, 1.05))
        + rect(400, 292, 400, 14, shade(p.near, 0.8))
        + rect(520, 250, 70, 50, "#cfd4d8", 'rx="6"')
        + rect(535, 240, 40, 14, "#8e959b", 'rx="3"')
        + "".join(
            f'<circle cx="{120 + i * 120}" cy="420" r="38" fill="{shade(p.mid, 0.95)}"/>'
            + rect(117 + i * 120, 420, 6, 70, shade(p.near, 0.8))
            for i in range(2)
        )
        + '<circle cx="140" cy="404" r="9" fill="#ffffff"/><circle cx="252" cy="404" r="9" fill="#ffffff"/>'
    )
    return bg, fg


def counter_scene(p: Palette, name: str, rng: random.Random, wall: str, accent: str, props: str) -> tuple[str, str]:
    floor = shade(wall, 0.75)
    bg = svg(
        interior(p, wall, floor, 2, rng) + sign(200, 18, 400, name, accent, "#ffffff") + props,
        interior_defs(p, wall, floor),
    )
    desk = shade(p.near, 1.15)
    fg = svg(
        rect(160, 310, 480, 110, desk, 'rx="6"')
        + rect(150, 300, 500, 16, shade(desk, 0.8), 'rx="4"')
        + rect(250, 250, 80, 52, "#26313a", 'rx="4"')
        + rect(256, 256, 68, 40, shade(p.sky_bottom, 1.2))
        + rect(285, 302, 10, 10, "#26313a")
        + rect(450, 280, 90, 20, "#ffffff", 'rx="2"')
        + rect(455, 270, 80, 12, "#f1efe8", 'rx="2"')
    )
    return bg, fg


def bank(p: Palette, location: Location, rng: random.Random) -> tuple[str, str]:
    name = location["name"]
    props = rect(60, 290, 90, 60, "#ffffff", 'rx="4" opacity="0.85"') + text(105, 325, "%", 26, p.water)
    return counter_scene(p, name, rng, shade(p.sky_bottom, 1.35), p.water, props)


def office(p: Palette, location: Location, rng: random.Random) -> tuple[str, str]:
    name = location["name"]
    board = rect(40, 270, 150, 80, "#c49a6c", 'rx="3"') + "".join(
        rect(52 + (i % 3) * 46, 280 + (i // 3) * 34, 38, 26, ["#fff7c2", "#ffffff", "#d7ecff"][i % 3]) for i in range(6)
    )
    return counter_scene(p, name, rng, shade(p.far, 1.55), shade(p.mid, 0.75), board)


def clinic(p: Palette, location: Location, rng: random.Random) -> tuple[str, str]:
    name = location["name"]
    cross = rect(85, 280, 60, 20, "#d9534f") + rect(105, 260, 20, 60, "#d9534f")
    bg, fg = counter_scene(p, name, rng, "#eef3f2", "#3f8f86", cross)
    chairs = "".join(
        rect(660 + i * 46, 380, 38, 40, "#7fb5ae", 'rx="6"') + rect(660 + i * 46, 340, 38, 44, "#93c4bd", 'rx="6"')
        for i in range(3)
    )
    return bg, fg.replace("</svg>", chairs + "</svg>")


def shop(p: Palette, location: Location, rng: random.Random) -> tuple[str, str]:
    name = location["name"]
    wall, floor = shade(p.mid, 1.2), shade(p.near, 1.1)
    product = hotspot(location, "enduit", "kit")
    found = PRICE.search(product["text"]) if product else None
    price = found.group(1) if found else ""
    tools = ""
    for row in range(3):
        y = 110 + row * 70
        tools += rect(60, y + 44, 680, 8, shade(p.near, 0.9))
        for i in range(12):
            colour = [p.water, "#c0392b", "#e6b422", p.far, "#7f8c8d"][(i * 7 + row) % 5]
            h = 20 + rng.randint(0, 22)
            tools += rect(72 + i * 56, y + 44 - h, 38, h, colour, 'rx="3"')
    bg = svg(
        rect(0, 0, W, 360, "url(#wall)")
        + rect(0, 360, W, 140, "url(#floor)")
        + tools
        + sign(200, 22, 400, name, shade(p.near, 0.85), "#f6e7c8"),
        interior_defs(p, wall, floor),
    )
    fg = svg(
        rect(470, 320, 300, 100, shade(p.near, 1.25), 'rx="4"')
        + rect(460, 308, 320, 16, shade(p.near, 0.9))
        + rect(80, 330, 90, 90, "#e6e1d6", 'rx="6"')
        + text(125, 380, price, 16, p.near)
        + '<path d="M560 300 L580 240 L600 300 Z" fill="#7f8c8d"/>'
        + rect(640, 270, 18, 40, "#e6b422", 'rx="3"')
    )
    return bg, fg


def hall(p: Palette, location: Location, rng: random.Random) -> tuple[str, str]:
    name = location["name"]
    stone = shade(p.mid, 1.25 if rng.random() < 0.5 else 0.95)
    columns = "".join(rect(210 + i * 80, 200, 30, 180, shade(stone, 1.15)) for i in range(5))
    windows = "".join(rect(225 + i * 80, 120, 50, 60, shade(p.sky_bottom, 0.9), 'rx="25"') for i in range(4))
    bg = svg(
        street(p, stone, rng)
        + rect(170, 100, 460, 280, stone)
        + f'<path d="M150 104 L400 30 L650 104 Z" fill="{shade(stone, 0.85)}"/>'
        + windows
        + columns
        + rect(370, 290, 60, 90, shade(p.near, 0.9), 'rx="30"')
        + sign(250, 196, 300, name, shade(stone, 0.6), "#ffffff"),
        gradient("sky", p.sky_top, p.sky_bottom),
    )
    fg = svg(
        rect(150, 380, 500, 18, shade(stone, 0.9))
        + rect(130, 398, 540, 18, shade(stone, 0.8))
        + rect(60, 330, 110, 70, "#ffffff", 'rx="4" opacity="0.92"')
        + rect(60, 330, 110, 14, p.water)
        + rect(112, 400, 6, 60, shade(p.near, 0.8))
        + f'<circle cx="720" cy="420" r="34" fill="{shade(p.far, 0.8)}"/>'
        + rect(716, 420, 8, 60, shade(p.near, 0.7))
    )
    return bg, fg


def library(p: Palette, location: Location, rng: random.Random) -> tuple[str, str]:
    name = location["name"]
    wall, floor = shade(p.near, 1.6), shade(p.near, 1.2)
    debate = hotspot(location, "debat", "debate")
    books = ""
    for case in range(3):
        x0 = 40 + case * 250
        books += rect(x0, 70, 220, 280, shade(p.near, 0.85))
        for row in range(5):
            y = 80 + row * 54
            x = x0 + 8
            while x < x0 + 206:
                bw = 8 + rng.randint(0, 10)
                colour = [p.water, "#8e3b46", "#c69c3f", p.far, "#4f6d4a", "#6b4f7a"][rng.randint(0, 5)]
                books += rect(x, y + rng.randint(0, 10), bw, 44 - rng.randint(0, 10), colour)
                x += bw + 2
            books += rect(x0, y + 44, 220, 6, shade(p.near, 0.7))
    bg = svg(
        rect(0, 0, W, 360, "url(#wall)")
        + rect(0, 360, W, 140, "url(#floor)")
        + books
        + sign(250, 16, 300, name, shade(p.near, 0.7), "#f3e6c8"),
        interior_defs(p, wall, floor),
    )
    fg = svg(
        rect(200, 340, 400, 20, shade(p.near, 1.1), 'rx="4"')
        + rect(220, 360, 14, 90, shade(p.near, 0.9))
        + rect(566, 360, 14, 90, shade(p.near, 0.9))
        + rect(330, 318, 60, 22, "#f5f0e1", 'rx="2"')
        + rect(400, 322, 50, 18, "#8e3b46", 'rx="2"')
        + '<circle cx="300" cy="320" r="14" fill="#f2d16b" opacity="0.9"/>'
        + rect(296, 320, 8, 22, shade(p.near, 0.6))
        + rect(640, 300, 120, 70, "#fff8e1", 'rx="4"')
        + fitted(700, 342, (debate["label"] if debate else "").upper(), 110, 14, "#8e3b46")
    )
    return bg, fg


def newsroom(p: Palette, location: Location, rng: random.Random) -> tuple[str, str]:
    name = location["name"]
    wall, floor = shade(p.far, 1.45), shade(p.near, 1.25)
    clippings = "".join(
        rect(60 + (i % 4) * 44, 270 + (i // 4) * 36, 36, 28, "#fbfaf5", f'transform="rotate({rng.randint(-6, 6)})"')
        for i in range(8)
    )
    bg = svg(
        interior(p, wall, floor, 2, rng) + sign(220, 16, 360, name, "#1f2a33", "#ffffff") + clippings,
        interior_defs(p, wall, floor),
    )
    papers = "".join(rect(560 + i * 6, 330 - i * 8, 120, 16, "#f4f1e8", 'rx="1"') for i in range(6))
    fg = svg(
        rect(240, 320, 300, 18, shade(p.near, 1.0))
        + rect(256, 338, 12, 100, shade(p.near, 0.8))
        + rect(512, 338, 12, 100, shade(p.near, 0.8))
        + rect(330, 270, 110, 52, "#2b2f33", 'rx="4"')
        + rect(336, 276, 98, 40, "#e9eef2")
        + "".join(rect(342, 282 + i * 8, 80 - i * 10, 4, "#9aa5ae") for i in range(4))
        + papers
        + '<circle cx="290" cy="306" r="12" fill="#ffffff"/><circle cx="290" cy="306" r="8" fill="#6f4e37"/>'
    )
    return bg, fg


SCENES: dict[str, Scene] = {
    "home": home,
    "cafe": cafe,
    "bank": bank,
    "office": office,
    "clinic": clinic,
    "shop": shop,
    "hall": hall,
    "library": library,
    "newsroom": newsroom,
}


def kind_of(stem: str) -> str:
    for prefix, kind in KINDS.items():
        if stem.startswith(prefix):
            return kind
    raise KeyError(f"no art template for {stem!r}; add it to KINDS")


def build(content: Path) -> list[Path]:
    written = []
    for city_file in sorted(content.glob("cities/*/city.yaml")):
        city = yaml.safe_load(city_file.read_text())
        palette = Palette(city["palette"])
        for district in city["districts"]:
            for location in district["locations"]:
                art = location.get("layer_art") or []
                if len(art) != 2:
                    continue
                stem = Path(art[0]).stem.removesuffix("_bg")
                rng = random.Random(location["key"])  # noqa: S311 (deterministic layout)
                layers = SCENES[kind_of(stem)](palette, location, rng)
                for rel, markup in zip(art, layers, strict=True):
                    path = content / "art" / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(markup)
                    written.append(path)
    return written


def main() -> None:
    written = build(ROOT / "content")
    print(f"wrote {len(written)} SVG layers under content/art/", file=sys.stderr)


if __name__ == "__main__":
    main()
