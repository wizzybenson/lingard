/** Offline cache for Glance mode: the quest queue and answers waiting to sync (SPEC §19.3). */
import AsyncStorage from "@react-native-async-storage/async-storage";

import type { Quest } from "@/api/types";

const QUEUE = "lingard.glance.queue";
const PENDING = "lingard.glance.pending";
const ANSWERED = "lingard.glance.answered";

export interface PendingAnswer {
  quest_id: string;
  answer: number;
  language: "fr" | "en";
  synced_at: string;
}

/** What the learner picked, and what the server said; `correct` and `answer` are null until an offline answer syncs. */
export interface Answered {
  choice: number;
  correct: boolean | null;
  answer: number | null;
}

export async function answeredQuests(): Promise<Record<string, Answered>> {
  const raw = await AsyncStorage.getItem(ANSWERED);
  return raw ? (JSON.parse(raw) as Record<string, Answered>) : {};
}

/** Remember an answer, forgetting quests that have left the queue so the store stays small. */
export async function rememberAnswer(questId: string, answered: Answered, queue: Quest[]): Promise<void> {
  const live = new Set(queue.map((q) => q.id));
  const kept = Object.entries(await answeredQuests()).filter(([id]) => live.has(id));
  await AsyncStorage.setItem(ANSWERED, JSON.stringify(Object.fromEntries([...kept, [questId, answered]])));
}

export async function cacheQueue(quests: Quest[]): Promise<void> {
  await AsyncStorage.setItem(QUEUE, JSON.stringify(quests));
}

export async function cachedQueue(): Promise<Quest[]> {
  const raw = await AsyncStorage.getItem(QUEUE);
  return raw ? (JSON.parse(raw) as Quest[]) : [];
}

export async function queueAnswer(answer: PendingAnswer): Promise<void> {
  const pending = await pendingAnswers();
  await AsyncStorage.setItem(PENDING, JSON.stringify([...pending, answer]));
}

export async function pendingAnswers(): Promise<PendingAnswer[]> {
  const raw = await AsyncStorage.getItem(PENDING);
  return raw ? (JSON.parse(raw) as PendingAnswer[]) : [];
}

/** Send queued answers; keeps the ones that still fail. Returns how many synced. */
export async function sync(send: (answer: PendingAnswer) => Promise<void>): Promise<number> {
  const pending = await pendingAnswers();
  const failed: PendingAnswer[] = [];
  for (const answer of pending) {
    try {
      await send(answer);
    } catch {
      failed.push(answer);
    }
  }
  await AsyncStorage.setItem(PENDING, JSON.stringify(failed));
  return pending.length - failed.length;
}
