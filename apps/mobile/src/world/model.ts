/** Renderer-independent world helpers: projection, parallax, marker placement. The 3D client will reuse these. */
import type { DistrictView, Location, NpcView, WorldView } from "./types";

export interface Size {
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

export const LAYERS = [
  { name: "sky", depth: 0.05 },
  { name: "far", depth: 0.2 },
  { name: "mid", depth: 0.5 },
  { name: "near", depth: 1 },
] as const;

export const MARKER_WIDTH = 188;
/** Height of a place's label pill; it sits above the place's point, which a small pin marks. */
export const MARKER_HEIGHT = 36;

/** Normalised (0–1) world coordinates → screen, with horizontal parallax for a layer depth. */
export function project(point: Point, size: Size, panX: number, depth = 1): Point {
  return { x: point.x * size.width + panX * depth, y: point.y * size.height };
}

export function clampPan(panX: number, size: Size, worldWidthFactor = 1.6): number {
  const max = 0;
  const min = -(worldWidthFactor - 1) * size.width;
  return Math.min(max, Math.max(min, panX));
}

export function unlockedLocations(view: WorldView): Location[] {
  return view.districts.filter((d: DistrictView) => d.unlocked).flatMap((d: DistrictView) => d.locations);
}

export interface Placed {
  location: Location;
  point: Point;
}

/** Unlocked districts sit side by side, one screen width each, in the order the world API lists them. Location
 * coordinates are normalised within their district, so district k spans x ∈ [k, k + 1]. */
export function placedLocations(view: WorldView): Placed[] {
  return view.districts
    .filter((d: DistrictView) => d.unlocked)
    .flatMap((d: DistrictView, i: number) =>
      d.locations.map((location: Location) => ({ location, point: { x: i + (location.x ?? 0.5), y: location.y ?? 0.5 } })),
    );
}

/** World width in screen widths: one per unlocked district, with parallax room even for a single district. */
export function worldWidth(view: WorldView): number {
  return Math.max(1.6, view.districts.filter((d: DistrictView) => d.unlocked).length);
}

export function npcsAt(view: WorldView, locationKey: string): NpcView[] {
  return view.npcs.filter((n: NpcView) => n.location_key === locationKey);
}

/** Left edge of a marker centred on ``x``, kept inside its district's screen so a name is never cut off. */
export function markerLeft(x: number, size: Size, width = MARKER_WIDTH, margin = 6): number {
  const screen = Math.floor(x / size.width) * size.width;
  return Math.max(screen + margin, Math.min(x - width / 2, screen + size.width - width - margin));
}

export function skyline(size: Size, seed: number, height: number, widthFactor: number): string {
  const r = (n: number) => Math.round(n * 10) / 10;
  const parts = [`M0 ${r(size.height)}`];
  let x = 0;
  let step = 0;
  while (x < size.width * (widthFactor + 0.1)) {
    const h = height * (0.6 + 0.4 * Math.abs(Math.sin(seed + step * 1.7)));
    parts.push(`L${r(x)} ${r(size.height - h)}`);
    x += 30 + 25 * Math.abs(Math.cos(seed * 3 + step));
    parts.push(`L${r(x)} ${r(size.height - h)}`);
    step += 1;
  }
  parts.push(`L${r(x)} ${r(size.height)}`, "Z");
  return parts.join(" ");
}
