"use client";

import { useEffect } from "react";

import { removeServiceWorkers, SERVICE_WORKER_ENABLED } from "@/lib/service-worker";

/** `pnpm dev` only: removes a service worker and its caches left from a production build on this address, then reloads
 * once so the page runs the dev code. Renders nothing; does nothing in production. */
export function DevServiceWorkerReset() {
  useEffect(() => {
    if (SERVICE_WORKER_ENABLED) return;
    const controlled = typeof navigator !== "undefined" && !!navigator.serviceWorker?.controller;
    removeServiceWorkers()
      .then((n) => {
        if (n > 0 && controlled) window.location.reload();
      })
      .catch(() => undefined);
  }, []);
  return null;
}
