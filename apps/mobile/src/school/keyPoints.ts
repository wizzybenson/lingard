import { router } from "expo-router";

import type { ApiClient } from "@/api/client";
import type { KeyPoint } from "@/api/types";
import type { IconName } from "@/ui/kit";

/** Each kind of key point's icon: outline while new, filled once opened. */
export const KIND_ICONS: Record<KeyPoint["kind"], [IconName, IconName]> = {
  grammar: ["book-outline", "book"],
  lexset: ["albums-outline", "albums"],
  function: ["chatbubbles-outline", "chatbubbles"],
};

/** Key points worth offering now: the ones not learned yet. */
export function unlearned(points: KeyPoint[] | null | undefined): KeyPoint[] {
  return (points ?? []).filter((k) => k.status !== "done");
}

/** Open a key-points lesson: the server builds it at once from the rule's authored key points (or returns the existing one). */
export async function openKeyPoint(api: ApiClient, nodeKey: string): Promise<void> {
  const { id } = await api.post<{ id: string }>(`/v1/key-points/${encodeURIComponent(nodeKey)}`, {});
  router.push({ pathname: "/lesson/[id]", params: { id } });
}
