/** Verbs a learner can tap anywhere a rule is taught (a lesson, a mission brief) to see the verb's full tables.
 * The index of a language's verb forms is fetched once and kept for the session. */
import { router } from "expo-router";
import { createContext, useContext, useEffect, useState } from "react";

import type { ApiClient } from "@/api/client";
import type { VerbIndex, VerbTables } from "@/api/types";


const cache = new Map<string, Promise<VerbIndex>>();

/** The language's verb index (and the tenses ``node`` is about); null while it loads or when there is none. */
export function useVerbIndex(api: ApiClient, language: string | null, node?: string): VerbIndex | null {
  const [index, setIndex] = useState<VerbIndex | null>(null);
  useEffect(() => {
    if (!language) return;
    let live = true;
    const key = `${language}|${node ?? ""}`;
    let request = cache.get(key);
    if (!request) {
      const query = node ? `?node=${encodeURIComponent(node)}` : "";
      request = api.get<VerbIndex>(`/v1/conjugations/${language}${query}`);
      request.catch(() => cache.delete(key)); // a failed fetch is tried again next time
      cache.set(key, request);
    }
    request.then((v) => live && setIndex(v)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [api, language, node]);
  return index;
}

const tables = new Map<string, Promise<VerbTables>>();

/** One verb's tables, fetched once per session; null while loading or if it failed. */
export function useVerbTables(api: ApiClient, language: string, verb: string | null | undefined): VerbTables | null {
  const [data, setData] = useState<VerbTables | null>(null);
  useEffect(() => {
    if (!verb) return;
    let live = true;
    const key = `${language}|${verb}`;
    let request = tables.get(key);
    if (!request) {
      request = api.get<VerbTables>(`/v1/conjugations/${language}/${encodeURIComponent(verb)}`);
      request.catch(() => tables.delete(key));
      tables.set(key, request);
    }
    request.then((v) => live && setData(v)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [api, language, verb]);
  return data;
}

export interface VerbLinks {
  index: Record<string, string> | null;
  open: (verb: string) => void;
}

/** What a screen teaching a rule gives the lines inside it: which words are verbs, and how to open one. */
export const VerbContext = createContext<VerbLinks>({ index: null, open: () => undefined });
export const useVerbLinks = () => useContext(VerbContext);

/** Open a verb's tables as a sheet over the screen, on the tense the rule is about. */
export function openVerb(language: string, verb: string, tense?: string): void {
  router.push({ pathname: "/verb/[language]/[key]", params: { language, key: verb, ...(tense && { tense }) } });
}
