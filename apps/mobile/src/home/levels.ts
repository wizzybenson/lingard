type Translate = (key: string, options?: Record<string, unknown>) => string;

/** A level range in words ("below 4", "6", "5 to 7"), never the "<4–8" shorthand. */
export function levelWords(t: Translate, low: number | null | undefined, high: number | null | undefined): string {
  if (low == null || high == null) return t("passport.notMeasured");
  const show = (n: number) => (n < 4 ? t("passport.below", { level: 4 }) : String(n));
  if (low === high || (low < 4 && high < 4)) return show(low);
  return t("passport.between", { low: show(low), high: show(high) });
}

/** How far the middle of the estimate is towards the goal, 0–1. Unknown counts as no progress yet. */
export function levelProgress(low: number | null | undefined, high: number | null | undefined, target: number): number {
  if (low == null && high == null) return 0;
  const from = low ?? high ?? 0;
  const to = high ?? from;
  return Math.max(0, Math.min(1, (from + to) / 2 / target));
}
