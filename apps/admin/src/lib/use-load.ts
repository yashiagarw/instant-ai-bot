"use client";

import { useCallback, useEffect, useState } from "react";

import { errorMessage } from "@/lib/api";

export type Load<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T };

/** Loads with `fetcher` (again when it changes, or on reload); null = nothing to load. */
export function useLoad<T>(fetcher: ((signal: AbortSignal) => Promise<T>) | null) {
  const [state, setState] = useState<Load<T>>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!fetcher) return;
    const ctrl = new AbortController();
    fetcher(ctrl.signal)
      .then((data) => setState({ kind: "ready", data }))
      .catch((e) => !ctrl.signal.aborted && setState({ kind: "error", message: errorMessage(e) }));
    return () => ctrl.abort();
  }, [fetcher, attempt]);
  const reload = useCallback(() => setAttempt((a) => a + 1), []);
  const set = useCallback((data: T) => setState({ kind: "ready", data }), []);
  return { state, reload, set };
}
