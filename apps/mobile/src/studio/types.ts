/** The sound gym's shapes, as ``/v1/studio/gym`` sends them (decision 0028). */

export type Features =
  | { kind: "vowel"; height: number; back: number; rounded: boolean; nasal?: boolean }
  | { kind: "diphthong"; from: string; to: string }
  | { kind: "consonant"; place: string; manner: string; voiced: boolean };

export interface How {
  lips?: string;
  tongue?: string;
  jaw?: string;
  voice?: string;
  air?: string;
  steps: string[];
  check: string;
}

export interface SoundGuide {
  phoneme: string;
  example: string;
  features: Features;
  how: How;
  confusions: Record<string, string>;
}

export interface MarkedWord {
  text: string;
  phonemes: string[];
  /** Which of the phonemes the drill trains. */
  targets: number[];
}

export interface GymText {
  text: string;
  words: MarkedWord[];
}

export interface DrillSummary {
  key: string;
  title: string;
  sounds: string[];
  examples: string[];
  stage: number;
  stages: number[];
  mastered: boolean;
  due: string | null;
  review_due: boolean;
  score: number | null;
}

export interface DrillView extends DrillSummary {
  guides: SoundGuide[];
  pairs: [string, string][];
  pair_texts: GymText[];
  features: Record<string, Features>;
  words: GymText[];
  phrases: GymText[];
  sentence: GymText;
  /** For a drill on the music of speech, the part it trains. */
  focus: MusicPart | null;
  passed_items: string[];
  needed: number;
}

export interface GymOverview {
  drills: DrillSummary[];
  workout: string[];
  sounds: Record<string, number>;
}

export interface ScoredSound {
  phoneme: string;
  score: number;
  heard_as?: string | null;
  /** False when the recogniser can't reliably tell this sound from its partner: compare by ear. */
  checked?: boolean;
}

export type MusicPart = "stress" | "emphasis" | "rhythm" | "intonation";
export type Movement = "rise" | "fall" | "level";

export interface Syllable {
  word: number;
  text: string;
  model: { length: number; weight: number; pitch: number | null };
  you: { length: number; weight: number; pitch: number | null };
}

export interface Music {
  syllables: Syllable[];
  stress: { score: number; words: { word: string; syllables: string[]; expected: number; yours: number }[] } | null;
  emphasis: { score: number; expected: string; yours: string } | null;
  rhythm: { score: number; pace: number; stretch: string } | null;
  intonation: { score: number; final: { expected: Movement | null; yours: Movement | null } } | null;
}

export interface ScoredWord {
  text: string;
  score: number | null;
  phonemes: ScoredSound[];
}

export interface Tip {
  phoneme: string;
  example: string;
  word: string;
  heard_as: string | null;
  text: string;
  steps: string[];
}

export interface Attempt {
  intelligibility: number;
  accent_proximity: number;
  intonation: number | null;
  words: ScoredWord[];
  tips: Tip[];
  pitch: { learner: number[]; reference: number[] };
  prosody: Music | null;
  good?: boolean;
  /** The trained sound can't be judged by machine (French é/è…): the take was clear, the sound is compared by ear. */
  by_ear?: boolean;
  progress?: { stage: number; passed_items: string[]; mastered: boolean; best: Record<string, number> };
  uri: string;
}

/** The ladder (``Stage`` on the server). */
export const STAGE = { learn: 0, hear: 1, words: 2, pairs: 3, phrases: 4, sentence: 5, mastered: 6 } as const;
export const STAGE_NAMES = ["learn", "hear", "words", "pairs", "phrases", "sentence"] as const;
export const GOOD = 70;
