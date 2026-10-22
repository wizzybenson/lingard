/** Whether the API can be reached right now. Every request reports it, so a lost connection is one fact the whole app
 * shares (a banner, quiet error boxes, screens that reload when it is back) rather than an error in every card. */
import { useSyncExternalStore } from "react";

let online = true;
const listeners = new Set<(online: boolean) => void>();

export function reportReachable(now: boolean): void {
  if (now === online) return;
  online = now;
  for (const listener of listeners) listener(now);
}

export function isOnline(): boolean {
  return online;
}

export function onConnection(listener: (online: boolean) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useOnline(): boolean {
  return useSyncExternalStore(onConnection, isOnline, isOnline);
}
