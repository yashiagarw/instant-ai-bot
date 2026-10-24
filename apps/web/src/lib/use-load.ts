"use client";

import { useCallback, useEffect, useState } from "react";

import { errorMessage } from "@/lib/api";

export type Load<T> = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: T };

/** Fetch with loading and error states; `key` null means nothing to load yet. */
export function useLoad<T>(key: string | null, fetcher: (signal: AbortSignal) => Promise<T>) {
  const [loaded, setLoaded] = useState<{ key: string; attempt: number; state: Load<T> } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (key === null) return;
    const ctrl = new AbortController();
    fetcher(ctrl.signal)
      .then((data) => setLoaded({ key, attempt, state: { status: "ready", data } }))
      .catch((e) => {
        if (!ctrl.signal.aborted) setLoaded({ key, attempt, state: { status: "error", message: errorMessage(e) } });
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` identifies what `fetcher` loads
  }, [key, attempt]);
  // A result for another key (the previous make) or an earlier attempt never shows: it is still loading.
  const state: Load<T> =
    loaded && loaded.key === key && loaded.attempt === attempt ? loaded.state : { status: "loading" };
  return { state, retry: useCallback(() => setAttempt((a) => a + 1), []) };
}
