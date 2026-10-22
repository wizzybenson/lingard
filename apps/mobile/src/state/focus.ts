/** The language the learner is working on now. One choice for the whole app: the city, the phone, the school, the
 * studio and the exam hall all follow it, and switching it anywhere switches it everywhere. Saved on the server
 * (``focus_language`` on ``/v1/me``), so it follows the learner across devices. */
import { useSyncExternalStore } from "react";

import type { CityEntry, Profile } from "@/api/types";
import type { ApiClient } from "@/api/client";
import { useApi } from "@/state/auth";
import { useCities } from "@/state/cities";

export type Language = CityEntry["language"];

let focus: Language | null = null;
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const snapshot = () => focus;

/** Takes the focus the server has for this learner (on sign-in and whenever the profile is read). */
export function adoptFocus(profile: Pick<Profile, "focus_language">): void {
  if (profile.focus_language && profile.focus_language !== focus) {
    focus = profile.focus_language;
    listeners.forEach((l) => l());
  }
}

export async function chooseFocus(api: ApiClient, language: Language): Promise<void> {
  if (language === focus) return;
  focus = language;
  listeners.forEach((l) => l());
  await api.patch("/v1/me", { focus_language: language });
}

export interface Focus {
  /** The focus language, or the first city's until the server has answered. */
  language: Language | null;
  /** The city where the focus language is spoken. */
  city: CityEntry | null;
  cities: CityEntry[];
  choose: (language: Language) => void;
}

export function useFocus(): Focus {
  const api = useApi();
  const cities = useCities();
  const chosen = useSyncExternalStore(subscribe, snapshot, snapshot);
  const all = cities.data ?? [];
  const city = all.find((c) => c.language === chosen) ?? all[0] ?? null;
  return {
    language: city?.language ?? chosen,
    city,
    cities: all,
    choose: (language) => void chooseFocus(api, language).catch(() => undefined),
  };
}
