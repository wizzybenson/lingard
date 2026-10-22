import { useCallback, useEffect, useRef, useState } from "react";

import { onConnection } from "@/api/connection";

export interface Resource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload(): void;
}

/** Minimal async data hook: load on mount, on ``reload`` and when the connection returns after a failure; ignores
 * results from superseded calls. */
export function useResource<T>(load: () => Promise<T>, deps: unknown[] = []): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const run = useCallback(() => {
    const mine = ++generation.current;
    setLoading(true);
    load()
      .then((value) => {
        if (mine === generation.current) {
          setData(value);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (mine === generation.current) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (mine === generation.current) setLoading(false);
      });
    // The caller's deps decide when to reload, like useEffect's own list.
    // eslint-disable-next-line react-hooks/exhaustive-deps, react-hooks/use-memo
  }, deps);
  useEffect(run, [run]);
  // What failed while the server was unreachable loads again by itself once it is back.
  const failed = error !== null;
  useEffect(() => (failed ? onConnection((online) => online && run()) : undefined), [failed, run]);
  return { data, error, loading, reload: run };
}
