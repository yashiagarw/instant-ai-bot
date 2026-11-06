// /sw.js under `pnpm dev` (scripts/service-worker.mjs --dev). Development has no service worker: chunk names do not
// change between edits, so a caching worker would keep serving old code. A browser that still has the worker from a
// production build (same localhost address) checks /sw.js on its next page load, gets this file instead and:
// takes over, deletes our caches, unregisters itself and reloads its open tabs once, so they get the dev code.

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      await self.clients.claim();
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k.startsWith("im-")).map((k) => caches.delete(k)));
      await self.registration.unregister();
      const windows = await self.clients.matchAll({ type: "window" });
      await Promise.all(windows.map((w) => w.navigate(w.url).catch(() => undefined)));
    })(),
  );
});
