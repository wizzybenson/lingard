/** Every error the app shows lives here, so it can be shown in one place (the status banner at the top) instead of in
 * a box wherever it happened. A screen raises one by rendering ``ErrorText``; it goes when the screen clears it, the
 * screen closes, or the learner dismisses it. */
import { useSyncExternalStore } from "react";

export interface ShownError {
  id: number;
  message: string;
  onRetry?: () => void;
}

let errors: ShownError[] = [];
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((listener) => listener());

export function raiseError(id: number, message: string, onRetry?: () => void): void {
  errors = [...errors.filter((e) => e.id !== id), { id, message, ...(onRetry && { onRetry }) }];
  emit();
}

export function clearError(id: number): void {
  if (!errors.some((e) => e.id === id)) return;
  errors = errors.filter((e) => e.id !== id);
  emit();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const snapshot = () => errors;

/** The errors raised now, oldest first. */
export function useErrors(): ShownError[] {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

let next = 0;
/** A new id for a place that can raise an error. */
export const errorId = (): number => ++next;
