/** Offline cache for Glance mode: the quest queue and answers waiting to sync (SPEC §19.3). */
import AsyncStorage from "@react-native-async-storage/async-storage";

import type { Quest } from "@/api/types";

const QUEUE = "lingard.glance.queue";
const PENDING = "lingard.glance.pending";

export interface PendingAnswer {
  quest_id: string;
  answer: number;
  language: "fr" | "en";
  synced_at: string;
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
