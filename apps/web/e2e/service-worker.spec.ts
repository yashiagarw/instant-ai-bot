// Phase 5.5: the service worker in a real browser (production build). It must never serve a page or file from an
// earlier build, and must keep the mechanic app's offline shell working.
import { expect, test } from "@playwright/test";

test("/sw.js is never cached and carries this build's id", async ({ request }) => {
  const res = await request.get("/sw.js");
  expect(res.ok()).toBe(true);
  expect(res.headers()["cache-control"]).toContain("no-store");
  const body = await res.text();
  expect(body).not.toContain('"__BUILD_ID__"'); // the placeholder was replaced
  expect(body).toMatch(/const BUILD = "[\w.-]+";/);
  expect(body).toContain("skipWaiting");
  expect(body).toContain("clients.claim");
});

test("offline: /m pages come from the shell (versioned caches only); customer pages are never served by the worker", async ({
  page,
  context,
}) => {
  await page.goto("/m/login");
  // Register as the signed-in mechanic app does, then reload so the page is controlled by the worker.
  await page.evaluate(async () => {
    await navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
    await navigator.serviceWorker.ready;
  });
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  await page.goto("/m/login"); // network-first: this copy is kept for offline use
  await expect(page.locator("h1")).toBeVisible();

  const names = await page.evaluate(() => caches.keys());
  const build = (await (await page.request.get("/sw.js")).text()).match(/const BUILD = "([\w.-]+)";/)![1];
  expect(names.length).toBeGreaterThan(0);
  for (const name of names) expect(name.endsWith(`-${build}`)).toBe(true); // nothing unversioned, nothing older

  await context.setOffline(true);
  await page.goto("/m/login");
  await expect(page.locator("h1")).toBeVisible(); // the saved /m page
  await page.goto("/m/never-visited");
  await expect(page.locator("h1")).toHaveText("आप ऑफ़लाइन हैं"); // the offline page
  // A customer page is not the worker's: offline it simply fails, it is never an old copy.
  await expect(page.goto("/")).rejects.toThrow();
  await context.setOffline(false);
});
