/** Game scoring shared by every School game (pure, unit-tested). */
import type { Game, GameItem } from "@/contracts/generated";

/** What an answer is judged on: the words and their spelling (accents included), not case, spacing or punctuation.
 * A dictation heard right but typed "Vous venez?" for « Vous venez ? », or without its comma, was marked wrong. */
export function normalise(answer: string): string {
  return answer
    .toLocaleLowerCase()
    .replace(/[’‘`]/g, "'")
    .replace(/[.,;:!?¿¡…«»“”"()\[\]–—]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function isCorrect(item: GameItem, answer: string): boolean {
  return normalise(answer) === normalise(item.answer);
}

/** Sentence race / spot-the-error choices: the answer plus distractors, deterministic order per item. */
export function choices(item: GameItem): string[] {
  const all = [...new Set([item.answer, ...(item.distractors ?? [])])];
  return all.sort((a, b) => (hash(item.prompt + a) % 997) - (hash(item.prompt + b) % 997));
}

function hash(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return h;
}

export interface GameResult {
  kind: Game["kind"];
  correct: number;
  total: number;
  missed: string[];
}

export function score(game: Game, answers: string[]): GameResult {
  const missed: string[] = [];
  let correct = 0;
  game.items.forEach((item, i) => {
    if (isCorrect(item, answers[i] ?? "")) correct += 1;
    else missed.push(item.node_key);
  });
  return { kind: game.kind, correct, total: game.items.length, missed };
}
