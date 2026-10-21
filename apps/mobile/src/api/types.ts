/** Shapes of API responses that are not generated from packages/contracts. */
import type { BandEstimate, CityEntry, Lesson, WorldView } from "@/contracts/generated";

export type { BandEstimate, CityEntry, Lesson, WorldView };

export interface SessionView {
  id: string;
  city: string | null;
  kind: string;
  status: "planning" | "ready" | "failed" | "ended";
  error?: string | null;
  scene_ids: string[];
  /** Every scene of the day is compiled; a ready day can start before that. */
  complete: boolean;
  notebook: Notebook | null;
}

export interface SceneView {
  id: string;
  city: string;
  location_key: string;
  npc_keys: string[];
  learner_goal: string;
  status: string;
  intensity: string;
  location_name: string;
  /** The kind of place (bank, clinic): the scene offers the words and phrases useful there before it starts. */
  location_kind: string | null;
  layer_art: string[];
  npc_name: string;
  npc_role: string;
  learner_band: number | null;
  mission: MissionBrief | null;
}

/** A scene as a mission: objectives, what can be won, and the coins it pays (never the hidden targets). */
export interface MissionBrief {
  objectives: string[];
  win: string | null;
  reward: number;
  bonus: number;
}

export interface Debrief {
  result: "accomplished" | "partial" | "not_done";
  objectives: { text: string; met: boolean }[];
  ending: string | null;
  coins: number;
}

export interface LiveTicket {
  livekit_url: string;
  room: string;
  token: string;
  scene_id: string;
}

export interface StepView {
  thread_id: string;
  done: boolean;
  prompt: ThreadPrompt | null;
  result: Record<string, unknown> | null;
}

export type ThreadPrompt =
  | {
      kind: "item";
      skill?: string;
      section?: string;
      minutes?: number;
      item: ServedItem;
    }
  | {
      kind: "set";
      section: string;
      minutes: number;
      progress: { done: number; total: number };
      set: ServedSet;
    }
  | {
      kind: "writing";
      prompt: string;
      min_words: number;
      minutes?: number;
      task?: string;
    }
  | {
      kind: "speaking";
      prompt: string;
      level?: number;
      part?: string;
      minutes?: number | number[];
      section?: string;
      scene_id?: string;
    }
  | { kind: "read_aloud"; text: string; asks_clone_consent: boolean };

export interface ServedItem {
  item_id: string;
  question: string;
  /** choice: one option; multi: ``picks`` options; text: a few typed words, at most ``word_limit``. */
  response?: "choice" | "multi" | "text";
  options: string[];
  picks?: number;
  word_limit?: number | null;
  /** Shown above this question where the instructions change within a set. */
  instructions?: string | null;
  text: string | null;
  audio_ref: string | null;
}

/** Questions sharing one text or recording, answered on one screen (Exam Hall). */
export interface ServedSet {
  set_id: string;
  part: string | null;
  instructions: string | null;
  /** A plan or chart drawn in monospace text. */
  figure: string | null;
  text: string | null;
  audio_ref: string | null;
  /** How many times the recording may be heard. */
  plays: number;
  questions: ServedItem[];
}

export type SetAnswer = number | number[] | string | null;

export interface Notebook {
  corrections: {
    node_key: string;
    learner_said: string;
    correction: string;
    explanation: string;
  }[];
  strengths: string[];
  encouragement: string;
  review_items: string[];
  lessons_suggested: string[];
}

export interface Passport {
  bands: BandEstimate[];
  sim_crs: number | null;
  crs_breakdown: Record<string, unknown> | null;
  disclaimer: string;
}

export interface Wallet {
  coins: number;
  stars_total: number;
  recent: { currency: string; delta: number; reason: string; at: string }[];
  items: ShopItem[];
}

/** An item in the shop (decision 0023); ``held`` and ``limit`` for what a learner keeps (freezes, flat upgrades). */
export interface ShopItem {
  key: string;
  price: number;
  held: number;
  limit: number | null;
}

/** A character met in the story, who can be given a gift. */
export interface Friend {
  npc_key: string;
  name: string;
  role: string;
  warmth: number;
  gifted_today: boolean;
}

export interface Quest {
  id: string;
  kind: "pick_correct" | "read";
  language: "fr" | "en";
  prompt: string;
  options: string[];
  text: string | null;
  node_key: string | null;
}

export interface LessonRow {
  id: string;
  node_key: string;
  status: string;
  content: Lesson;
}

/** One step of the key-points path: a grammar rule taught before a scene needs it. */
export interface KeyPoint {
  node_key: string;
  /** A rule, a set of words, or a way of saying something. */
  kind: "grammar" | "lexset" | "function";
  title: string;
  band: number;
  /** At the learner's level: taught before the next story day. */
  core: boolean;
  /** One level up: a look ahead. */
  preview: boolean;
  status: "new" | "open" | "done";
  lesson_id: string | null;
  /** Kinds of place where this is useful: the journey offers it there. */
  places: string[];
}

export interface Profile {
  display_name: string;
  role: string;
  /** null until the learner chooses; the app then shows the device language and saves it. */
  ui_locale: "en" | "fr" | "ar" | null;
  target_bands: Record<string, Record<string, number>>;
  crs_inputs: Record<string, unknown>;
  model_accent: Record<string, string>;
  consents: {
    voice_clone: boolean;
    audio_retention_extended: boolean;
    friends_league: boolean;
  };
  intensity_cap: "calm" | "tense" | "heated";
  l1: string;
  language_bands: Record<string, number>;
  exam_dates: Record<string, string>;
}

export type SkillStatus = "met" | "close" | "behind" | "unknown";

export interface Today {
  /** Coins earned so far, shown beside the streak. */
  coins: number;
  /** Spare streak freezes bought in the shop. */
  freezes: number;
  streak: number;
  practised_today: boolean;
  reviews_due: number;
  lessons_waiting: number;
  goals: {
    pack: string;
    pack_name: string;
    exam_date: string | null;
    days_left: number | null;
    skills: {
      skill: string;
      target: number;
      level_low: number | null;
      level_high: number | null;
      status: SkillStatus;
    }[];
  }[];
  next_step: "set_goal" | "placement" | "key_points" | "lesson" | "story";
  /** The first rule at the learner's level not yet learned (when next_step is key_points). */
  next_key_point: { node_key: string; title: string } | null;
  onboarding: { goal: boolean; placement: boolean; first_story: boolean };
}

export interface WritingTask {
  pack: string;
  pack_name: string;
  task_id: string;
  kind: string;
  min_words: number;
  suggested_minutes: number;
  prompts: string[];
  /** The kind of task each prompt practises, in the same order (formal letter, problem–solution essay…). */
  prompt_variants: (string | null)[];
}

/** An exam as a full mock runs it: sections in the official order with their timing (GET /v1/exams/formats). */
export interface ExamFormat {
  pack: string;
  name: string;
  total_minutes: number;
  sections: {
    id: string;
    skill: "listening" | "reading" | "writing" | "speaking";
    minutes: number;
    questions: number | null;
    tasks: number;
  }[];
}
