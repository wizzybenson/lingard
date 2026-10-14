/** Exam-runner helpers: timers and word counts (pure). */
export function wordCount(text: string): number {
  return (text.match(/[\p{L}\p{N}'’-]+/gu) ?? []).length;
}

export function remaining(startedAt: number, minutes: number, now: number = Date.now()): number {
  return Math.max(0, Math.round(minutes * 60 - (now - startedAt) / 1000));
}

export function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
