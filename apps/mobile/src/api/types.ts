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
  layer_art: string[];
  npc_name: string;
  npc_role: string;
  learner_band: number | null;
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
  | { kind: "item"; skill?: string; section?: string; minutes?: number; item: ServedItem }
  | { kind: "writing"; prompt: string; min_words: number; minutes?: number; task?: string }
  | { kind: "speaking"; prompt: string; level?: number; part?: string; minutes?: number | number[] }
  | { kind: "read_aloud"; text: string; asks_clone_consent: boolean };

export interface ServedItem {
  item_id: string;
  question: string;
  options: string[];
  text: string | null;
  audio_ref: string | null;
}

export interface Notebook {
  corrections: { node_key: string; learner_said: string; correction: string; explanation: string }[];
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
  shop: Record<string, number>;
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

export interface Profile {
  display_name: string;
  role: string;
  ui_locale: "en" | "fr" | "ar";
  target_bands: Record<string, Record<string, number>>;
  crs_inputs: Record<string, unknown>;
  model_accent: Record<string, string>;
  consents: { voice_clone: boolean; audio_retention_extended: boolean; friends_league: boolean };
  intensity_cap: "calm" | "tense" | "heated";
  l1: string;
  language_bands: Record<string, number>;
  exam_dates: Record<string, string>;
}

export type SkillStatus = "met" | "close" | "behind" | "unknown";

export interface Today {
  streak: number;
  practised_today: boolean;
  reviews_due: number;
  lessons_waiting: number;
  goals: {
    pack: string;
    pack_name: string;
    exam_date: string | null;
    days_left: number | null;
    skills: { skill: string; target: number; level_low: number | null; level_high: number | null; status: SkillStatus }[];
  }[];
  next_step: "set_goal" | "placement" | "reviews" | "lesson" | "story";
  onboarding: { goal: boolean; placement: boolean; first_story: boolean };
}

export interface WritingTask {
  pack: string;
  pack_name: string;
  task_id: string;
  kind: string;
  min_words: number;
  prompts: string[];
}
