"use client";

// The site's service worker (/sw.js, written by scripts/service-worker.mjs): offline shell for /m and web push.
// Never registered under `pnpm dev`: chunk names do not change between edits there, so a worker would keep serving old
// code (Phase 5.5). DevServiceWorkerReset removes one a browser kept from a production build.

export const SERVICE_WORKER_ENABLED = process.env.NODE_ENV !== "development";

export function serviceWorkerSupported(): boolean {
  return SERVICE_WORKER_ENABLED && typeof navigator !== "undefined" && "serviceWorker" in navigator;
}

/** Register (or update) the worker. updateViaCache "none": the browser always asks the server for /sw.js, so a new
 * build is picked up on the next page load. Null where workers are off or unsupported. */
export function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!serviceWorkerSupported()) return Promise.resolve(null);
  return navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
}

export function getServiceWorkerRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (!serviceWorkerSupported()) return Promise.resolve(null);
  return navigator.serviceWorker.getRegistration("/").then((r) => r ?? null);
}

/** Development only: unregister any worker and delete our caches (a leftover from a production build on the same
 * localhost address would otherwise serve stale code). */
export async function removeServiceWorkers(): Promise<number> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return 0;
  const regs = await navigator.serviceWorker.getRegistrations();
  await Promise.all(regs.map((r) => r.unregister()));
  if (typeof caches !== "undefined") {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k.startsWith("im-")).map((k) => caches.delete(k)));
  }
  return regs.length;
}
