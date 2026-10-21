/** Finding the verbs in a line of teaching (no React, no navigation): what a learner can tap to open a verb. */

/** A run of text: highlighted (``**x**`` in the content) or a verb that opens its tables. */
export interface Piece {
  text: string;
  strong?: boolean;
  verb?: string;
}

/** An elided pronoun or article written onto the word (j'ai, qu'il, n'est): the verb is the rest. */
const ELIDED = /^(?:j|l|n|m|t|s|qu|d|c)['’]/i;
const WORD = /([\p{L}\p{M}]+(?:['’-][\p{L}\p{M}]+)*)/u;

/** The verb a written word belongs to, if any: « J'habite » → habiter, « est-ce » → être. */
export function verbOf(word: string, index: Record<string, string>): string | undefined {
  const lower = word.toLocaleLowerCase();
  const bare = lower.replace(ELIDED, "");
  return index[lower] ?? index[bare] ?? index[bare.split("-")[0] ?? ""];
}

/** Split a line into its highlighted parts and its verbs. Without an index, only the highlights. */
export function pieces(text: string, index: Record<string, string> | null): Piece[] {
  const out: Piece[] = [];
  const push = (piece: Piece) => {
    const last = out[out.length - 1];
    if (last && !last.verb && !piece.verb && !!last.strong === !!piece.strong) last.text += piece.text;
    else out.push(piece);
  };
  text.split("**").forEach((run, i) => {
    const strong = i % 2 === 1;
    if (!run) return;
    for (const token of run.split(WORD)) {
      if (!token) continue;
      const verb = index && WORD.test(token) ? verbOf(token, index) : undefined;
      push(strong ? { text: token, strong, ...(verb && { verb }) } : { text: token, ...(verb && { verb }) });
    }
  });
  return out;
}

/** The language a node, lesson or rule belongs to: its key's first part (fr.grammar.…). */
export const languageOf = (nodeKey: string): string => nodeKey.split(".")[0] ?? "";
