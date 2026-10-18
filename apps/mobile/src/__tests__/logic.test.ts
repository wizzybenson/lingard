import { pinWeakness } from "@/auth/pin";
import { pinStillFresh } from "@/auth/store";
import { appendCaption, captionOpacity, parseCaption } from "@/live/captions";
import type { Game } from "@/contracts/generated";
import { choices, isCorrect, score } from "@/games/engine";
import { levelProgress, levelRange, levelWords } from "@/home/levels";
import { clock, remaining, wordCount } from "@/games/exam";
import ar from "@/i18n/ar.json";
import en from "@/i18n/en.json";
import fr from "@/i18n/fr.json";
import { clampPan, hitTest, initials, placedLocations, project, skyline, worldWidth } from "@/world/model";
import type { WorldView } from "@/world/types";

jest.mock("expo-secure-store", () => ({}));
jest.mock("expo-local-authentication", () => ({}));

test.each(["000000", "123456", "654321", "890123", "111222", "121212", "123123", "112233", "123321", "12345"])(
  "weak PIN %s rejected (same cases as the server)",
  (pin) => expect(pinWeakness(pin)).not.toBeNull(),
);

test.each(["613470", "730264", "195837"])("reasonable PIN %s accepted", (pin) => expect(pinWeakness(pin)).toBeNull());

test("PIN must be re-entered after 30 days", () => {
  const now = new Date("2026-10-14T00:00:00Z");
  expect(pinStillFresh("2026-10-01T00:00:00Z", now)).toBe(true);
  expect(pinStillFresh("2026-09-10T00:00:00Z", now)).toBe(false);
  expect(pinStillFresh(null, now)).toBe(false);
});

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) => (typeof v === "object" ? keys(v as object, `${prefix}${k}.`) : [`${prefix}${k}`]));
}

test("every UI string exists in English and French", () => {
  expect(keys(fr).sort()).toEqual(keys(en).sort());
});

test("Arabic covers every English string (with its own plural forms)", () => {
  const base = (k: string) => k.replace(/_(zero|one|two|few|many|other)$/, "");
  expect([...new Set(keys(ar).map(base))].sort()).toEqual([...new Set(keys(en).map(base))].sort());
});

const world: WorldView = {
  city: "rivemont",
  name: "Rivemont",
  hour: 12,
  palette: { sky: ["#f6d7b0", "#8fb8de"], far: "#6d8fb3", mid: "#b5835a", near: "#5b4636", water: "#3e6f97" },
  districts: [
    { key: "rivemont.vieux_port", name: "Vieux-Port", unlocked: true, min_band: 1,
      locations: [{ key: "a", name: "A", description: "", layer_art: [], hotspots: [], x: 0.2, y: 0.5 },
                  { key: "b", name: "B", description: "", layer_art: [], hotspots: [], x: 0.8, y: 0.5 }] },
    { key: "rivemont.saint_roch", name: "Saint-Roch", unlocked: false, min_band: 6, locations: [] },
  ],
  npcs: [{ key: "landlord_martin", name: "Martin Lefebvre", role: "propriétaire", location_key: "a" }],
};

test("projection, parallax, pan clamping and hit-testing", () => {
  const size = { width: 400, height: 300 };
  expect(project({ x: 0.5, y: 0.5 }, size, -100, 0.5)).toEqual({ x: 150, y: 150 });
  expect(clampPan(50, size)).toBe(0);
  expect(clampPan(-1000, size)).toBeCloseTo(-240);
  expect(hitTest(world, { x: 82, y: 152 }, size, 0)?.key).toBe("a");
  expect(hitTest(world, { x: 82 - 200, y: 152 }, size, -200)?.key).toBe("a");
  expect(hitTest(world, { x: 200, y: 40 }, size, 0)).toBeNull();
  expect(initials("Martin Lefebvre")).toBe("ML");
});

test("unlocked districts sit side by side so their markers never overlap", () => {
  const size = { width: 400, height: 300 };
  const both: WorldView = {
    ...world,
    districts: [
      world.districts[0]!,
      { key: "rivemont.saint_roch", name: "Saint-Roch", unlocked: true, min_band: 6,
        locations: [{ key: "c", name: "C", description: "", layer_art: [], hotspots: [], x: 0.2, y: 0.5 }] },
    ],
  };  // prettier-ignore
  expect(worldWidth(world)).toBe(1.6);
  expect(worldWidth(both)).toBe(2);
  expect(placedLocations(both).map((p) => [p.location.key, p.point.x])).toEqual([["a", 0.2], ["b", 0.8], ["c", 1.2]]);
  expect(hitTest(both, { x: 82, y: 152 }, size, 0)?.key).toBe("a");
  expect(hitTest(both, { x: 82, y: 152 }, size, -400)?.key).toBe("c");
  expect(clampPan(-1000, size, worldWidth(both))).toBe(-400);
});

test("game scoring normalises answers and reports missed nodes", () => {
  const game: Game = {
    kind: "conjugation_duel",
    items: [
      { prompt: "nous — aller (imparfait)", answer: "allions", distractors: [], node_key: "fr.grammar.imparfait" },
      { prompt: "je — être (imparfait)", answer: "étais", distractors: [], node_key: "fr.grammar.imparfait" },
    ],
    time_limit_s: 60,
  };
  expect(isCorrect(game.items[0]!, "  Allions ")).toBe(true);
  const result = score(game, ["allions", "etais"]);
  expect(result).toEqual({ kind: "conjugation_duel", correct: 1, total: 2, missed: ["fr.grammar.imparfait"] });
  const item = { prompt: "Je n'ai pas du temps.", answer: "Je n'ai pas de temps.", distractors: ["Je n'ai pas du temps."], node_key: "x" };
  expect(choices(item).sort()).toEqual([item.answer, item.distractors[0]].sort());
  expect(choices(item)).toEqual(choices(item));
});

test("captions parse, roll and fade by band", () => {
  const payload = new TextEncoder().encode(JSON.stringify({ type: "caption", speaker: "npc", text: "Bonjour." }));
  const caption = parseCaption(payload, 1);
  expect(caption).toEqual({ speaker: "npc", text: "Bonjour.", at: 1 });
  expect(parseCaption(new TextEncoder().encode("garbage"))).toBeNull();
  let log = [] as ReturnType<typeof appendCaption>;
  for (let i = 0; i < 10; i += 1) log = appendCaption(log, { speaker: "npc", text: `${i}`, at: i });
  expect(log.map((c) => c.text)).toEqual(["4", "5", "6", "7", "8", "9"]);
  expect(captionOpacity(4)).toBe(1);
  expect(captionOpacity(9)).toBe(0);
});

test("exam helpers", () => {
  expect(wordCount("Dear Mr Harris, I'm writing — about the flat.")).toBe(8);
  expect(wordCount("Je m'appelle Sam et j'habite à Rivemont.")).toBe(7);
  expect(remaining(0, 1, 30_000)).toBe(30);
  expect(clock(65)).toBe("1:05");
});

test("goal chips show CLB/NCLC ranges, with <4 below the conversion tables", () => {
  expect(levelRange(null, null)).toBe("–");
  expect(levelRange(7, 7)).toBe("7");
  expect(levelRange(3, 6)).toBe("<4–6");
});

test("skyline is a closed SVG path spanning the whole world, the same every time", () => {
  const size = { width: 300, height: 340 };
  const path = skyline(size, 1, 150, 1.6);
  expect(path.startsWith("M0 340 L")).toBe(true);
  expect(path.endsWith(" Z")).toBe(true);
  const xs = [...path.matchAll(/L([\d.]+) /g)].map((m) => Number(m[1]));
  expect(Math.max(...xs)).toBeGreaterThanOrEqual(300 * 1.7);
  expect(skyline(size, 1, 150, 1.6)).toBe(path);
});

test("levels read as words, never the <4–8 shorthand", () => {
  const en = (key: string, o?: Record<string, unknown>) =>
    ({ "passport.notMeasured": "not measured yet", "passport.below": `below ${o?.level}`, "passport.between": `${o?.low} to ${o?.high}` })[key] ?? key;
  expect(levelWords(en, null, null)).toBe("not measured yet");
  expect(levelWords(en, 2, 3)).toBe("below 4");
  expect(levelWords(en, 2, 8)).toBe("below 4 to 8");
  expect(levelWords(en, 6, 6)).toBe("6");
  expect(levelWords(en, 5, 7)).toBe("5 to 7");
  const fr = (key: string, o?: Record<string, unknown>) =>
    ({ "passport.notMeasured": "pas encore mesuré", "passport.below": `moins de ${o?.level}`, "passport.between": `de ${o?.low} à ${o?.high}` })[key] ?? key;
  expect(levelWords(fr, 5, 7)).toBe("de 5 à 7");
});

test("progress to a goal uses the middle of the estimate, so a wide range never looks reached", () => {
  expect(levelProgress(null, null, 7)).toBe(0);
  expect(levelProgress(3, 8, 7)).toBeCloseTo(5.5 / 7);
  expect(levelProgress(8, 9, 7)).toBe(1);
});
