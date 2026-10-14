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

export function npcsAt(view: WorldView, locationKey: string): NpcView[] {
  return view.npcs.filter((n: NpcView) => n.location_key === locationKey);
}

/** The location whose marker contains the tap, nearest first; null when the tap hits nothing. */
export function hitTest(view: WorldView, tap: Point, size: Size, panX: number): Location | null {
  let best: { location: Location; distance: number } | null = null;
  for (const location of unlockedLocations(view)) {
    const centre = project({ x: location.x ?? 0.5, y: location.y ?? 0.5 }, size, panX);
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

/** Palette per city so Ashford and Rivemont feel different without art assets. */
export function palette(city: string): { sky: [string, string]; far: string; mid: string; near: string; water: string } {
  return city === "rivemont"
    ? { sky: ["#f6d7b0", "#8fb8de"], far: "#6d8fb3", mid: "#b5835a", near: "#5b4636", water: "#3e6f97" }
    : { sky: ["#dfe6ee", "#9aa9bd"], far: "#7c8a9c", mid: "#9a6b52", near: "#47423f", water: "#566f7f" };
}
