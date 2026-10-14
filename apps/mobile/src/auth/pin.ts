/** Mirror of the server's weak-PIN policy so learners get instant feedback (the server remains authoritative). */
export function pinWeakness(pin: string): string | null {
  if (!/^\d{6}$/.test(pin)) return "pin.mustBeSixDigits";
  const digits = [...pin].map(Number);
  if (new Set(digits).size <= 2) return "pin.tooFewDigits";
  const steps = new Set(digits.slice(1).map((d, i) => (d - digits[i]! + 10) % 10));
  if (steps.size === 1 && (steps.has(1) || steps.has(9))) return "pin.sequence";
  if (pin.slice(0, 3) === pin.slice(3)) return "pin.repeats";
  const doubled = pin[0] === pin[1] && pin[2] === pin[3] && pin[4] === pin[5];
  if (doubled || pin.slice(0, 3) === [...pin.slice(3)].reverse().join("")) return "pin.pattern";
  return null;
}
