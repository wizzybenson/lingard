/** Caption handling: parse data-channel messages, keep a short rolling log, fade by learner band (SPEC §19.2). */
export interface Caption {
  speaker: "npc" | "learner";
  text: string;
  at: number;
}

export function parseCaption(payload: Uint8Array, now: number = Date.now()): Caption | null {
  try {
    const data = JSON.parse(new TextDecoder().decode(payload)) as { type?: string; speaker?: string; text?: string };
    if (data.type !== "caption" || typeof data.text !== "string") return null;
    if (data.speaker !== "npc" && data.speaker !== "learner") return null;
    return { speaker: data.speaker, text: data.text, at: now };
  } catch {
    return null;
  }
}

export function appendCaption(log: Caption[], caption: Caption, limit = 6): Caption[] {
  return [...log, caption].slice(-limit);
}

/** Captions fade as the learner's band rises: full at ≤ 4, gone by 9 (the learner can still toggle them on). */
export function captionOpacity(band: number): number {
  return Math.max(0, Math.min(1, (9 - band) / 5));
}
