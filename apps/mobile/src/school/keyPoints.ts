import { router } from "expo-router";

import type { ApiClient } from "@/api/client";

/** Open a key-points lesson: the server builds it at once from the rule's authored key points (or returns the existing one). */
export async function openKeyPoint(api: ApiClient, nodeKey: string): Promise<void> {
  const { id } = await api.post<{ id: string }>(`/v1/key-points/${encodeURIComponent(nodeKey)}`, {});
  router.push({ pathname: "/lesson/[id]", params: { id } });
}
