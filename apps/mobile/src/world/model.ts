/** Renderer-independent world helpers: projection, parallax, hit-testing. The 3D client will reuse these. */
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

export const MARKER_RADIUS = 26;

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

/** The location whose marker contains the tap, nearest first; null when the tap hits nothing. */
export function hitTest(view: WorldView, tap: Point, size: Size, panX: number): Location | null {
  let best: { location: Location; distance: number } | null = null;
  for (const { location, point } of placedLocations(view)) {
    const centre = project(point, size, panX);
    const distance = Math.hypot(centre.x - tap.x, centre.y - tap.y);
    if (distance <= MARKER_RADIUS * 1.6 && (!best || distance < best.distance)) best = { location, distance };
  }
  return best?.location ?? null;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
