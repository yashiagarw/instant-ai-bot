// Phase 5.5: the service worker never serves pages or built files from an earlier build, and does nothing under
// `pnpm dev`. Runs the real /sw.js source (scripts/service-worker.mjs) in a fake worker environment.
import { afterEach, describe, expect, test, vi } from "vitest";

import { newBuildId, serviceWorkerSource } from "../../scripts/service-worker.mjs";

const ORIGIN = "https://im.test";

class FakeCache {
  entries = new Map<string, Response>();
  private key(r: RequestInfo | URL) {
    return typeof r === "string" ? new URL(r, ORIGIN).href : r instanceof URL ? r.href : r.url;
  }
  async match(r: RequestInfo | URL) {
    return this.entries.get(this.key(r))?.clone();
  }
  async put(r: RequestInfo | URL, res: Response) {
    this.entries.set(this.key(r), res);
  }
  async addAll(rs: RequestInfo[]) {
    for (const r of rs) await this.put(r, await network(r));
  }
}

class FakeCaches {
  stores = new Map<string, FakeCache>();
  async open(name: string) {
    if (!this.stores.has(name)) this.stores.set(name, new FakeCache());
    return this.stores.get(name)!;
  }
  async keys() {
    return [...this.stores.keys()];
  }
  async delete(name: string) {
    return this.stores.delete(name);
  }
}

// The network: every URL answers with its own path and a version, or fails when offline.
let online = true;
let serverVersion = "build-1";
async function network(r: RequestInfo | URL): Promise<Response> {
  if (!online) throw new TypeError("Failed to fetch");
  const url = new URL(typeof r === "string" ? r : r instanceof URL ? r.href : r.url, ORIGIN);
  const res = new Response(`${url.pathname} from ${serverVersion}`, { status: 200 });
  Object.defineProperty(res, "type", { value: "basic" });
  return res;
}

type Listener = (event: Record<string, unknown>) => void;

/** One installed worker: its listeners, the browser-side spies, and a way to send it events. */
function worker(source: string, caches: FakeCaches) {
  const listeners: Record<string, Listener[]> = {};
  const windows = [{ url: `${ORIGIN}/m`, navigate: vi.fn(async () => undefined) }];
  const self = {
    addEventListener: (type: string, fn: Listener) => (listeners[type] ??= []).push(fn),
    skipWaiting: vi.fn(async () => undefined),
    clients: { claim: vi.fn(async () => undefined), matchAll: vi.fn(async () => windows), openWindow: vi.fn() },
    registration: { unregister: vi.fn(async () => true), showNotification: vi.fn() },
    location: { origin: ORIGIN },
  };
  const fetch = vi.fn((r: RequestInfo | URL) => network(r));
  // In a worker, relative URLs resolve against the worker's own address.
  class WorkerRequest extends Request {
    constructor(input: string, init?: RequestInit) {
      super(new URL(input, ORIGIN), init);
    }
  }
  new Function("self", "caches", "fetch", "Request", source)(self, caches, fetch, WorkerRequest);

  async function fire(type: string, extra: Record<string, unknown> = {}) {
    const waits: Promise<unknown>[] = [];
    let response: Promise<Response> | null = null;
    const event = { ...extra, waitUntil: (p: Promise<unknown>) => waits.push(p), respondWith: (p: Promise<Response>) => (response = p) };
    for (const fn of listeners[type] ?? []) fn(event);
    await Promise.all(waits);
    return response as Promise<Response> | null;
  }
  // What the worker reads from a request: its method, address and mode ("navigate" for pages).
  const get = (path: string, mode: RequestMode = "no-cors", method = "GET") =>
    fire("fetch", { request: { method, mode, url: new URL(path, ORIGIN).href } as Request });
  return { self, fire, get, fetch, windows };
}

async function install(build: string, caches: FakeCaches) {
  const w = worker(serviceWorkerSource({ build }), caches);
  await w.fire("install");
  await w.fire("activate");
  return w;
}

afterEach(() => {
  online = true;
  serverVersion = "build-1";
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("production worker", () => {
  test("each build is a different worker file, with caches named after the build", async () => {
    expect(serviceWorkerSource({ build: "a1" })).not.toBe(serviceWorkerSource({ build: "b2" }));
    expect(newBuildId()).not.toBe(newBuildId());
    expect(() => serviceWorkerSource({ build: '"; evil()' })).toThrow(/invalid build id/);
    const caches = new FakeCaches();
    const w = await install("a1", caches);
    expect(await caches.keys()).toEqual(["im-m-shell-a1"]);
    expect(w.self.skipWaiting).toHaveBeenCalled(); // takes over at once
    expect(w.self.clients.claim).toHaveBeenCalled();
    expect(await (await caches.open("im-m-shell-a1")).match("/m/offline.html")).toBeDefined();
  });

  test("activating deletes every cache of earlier builds (and the old unversioned ones), not other sites' caches", async () => {
    const caches = new FakeCaches();
    for (const name of ["im-static-v1", "im-m-shell-v1", "im-static-old", "im-m-shell-old", "someone-else"]) await caches.open(name);
    await install("new", caches);
    expect((await caches.keys()).sort()).toEqual(["im-m-shell-new", "someone-else"]);
  });

  test("customer pages, API calls and non-GET requests always go to the network (not handled)", async () => {
    const w = await install("a1", new FakeCaches());
    expect(await w.get("/", "navigate")).toBeNull();
    expect(await w.get("/hi/diagnose", "navigate")).toBeNull();
    expect(await w.get("/diagnose/abc/result", "navigate")).toBeNull();
    expect(await w.get("https://api.example/api/categories")).toBeNull();
    expect(await w.get("/_next/static/chunks/a.js", "no-cors", "POST")).toBeNull();
    expect(await w.get("/diagnose?_rsc=1")).toBeNull(); // page data for client navigations
  });

  test("/m pages: network first, the saved copy when offline, then the offline page", async () => {
    const w = await install("a1", new FakeCaches());
    expect(await (await w.get("/m/offers", "navigate"))!.text()).toBe("/m/offers from build-1");
    online = false;
    expect(await (await w.get("/m/offers?tab=2", "navigate"))!.text()).toBe("/m/offers from build-1");
    expect(await (await w.get("/m/profile", "navigate"))!.text()).toBe("/m/offline.html from build-1");
  });

  test("built files come from the cache, but never from an earlier build's cache", async () => {
    const caches = new FakeCaches();
    const old = await install("build-1", caches);
    expect(await (await old.get("/_next/static/chunks/app.js"))!.text()).toBe("/_next/static/chunks/app.js from build-1");
    expect(await (await old.get("/_next/static/chunks/app.js"))!.text()).toBe("/_next/static/chunks/app.js from build-1");
    expect(old.fetch).toHaveBeenCalledTimes(1); // the second read came from the cache

    // A deploy: the server has new files under the same name (as `next dev` does between edits).
    serverVersion = "build-2";
    const next = await install("build-2", caches);
    expect(await (await next.get("/_next/static/chunks/app.js"))!.text()).toBe("/_next/static/chunks/app.js from build-2");
    expect(await caches.keys()).not.toContain("im-static-build-1");
    // And the /m offline copy is the new build's too.
    online = false;
    expect(await (await next.get("/m/anything", "navigate"))!.text()).toBe("/m/offline.html from build-2");
  });

  test("push and notification taps still work", async () => {
    const w = await install("a1", new FakeCaches());
    await w.fire("push", { data: { json: () => ({ title: "Mechanic on the way", url: "/track/1", tag: "r1" }) } });
    expect(w.self.registration.showNotification).toHaveBeenCalledWith(
      "Mechanic on the way",
      expect.objectContaining({ tag: "r1", data: { url: "/track/1" } }),
    );
  });
});

describe("pnpm dev", () => {
  test("the dev /sw.js removes a worker left from a production build: caches, registration, then reloads tabs", async () => {
    const caches = new FakeCaches();
    for (const name of ["im-static-b1", "im-m-shell-b1", "someone-else"]) await caches.open(name);
    const w = worker(serviceWorkerSource({ build: "dev", dev: true }), caches);
    await w.fire("install");
    await w.fire("activate");
    expect(await caches.keys()).toEqual(["someone-else"]);
    expect(w.self.registration.unregister).toHaveBeenCalled();
    expect(w.windows[0].navigate).toHaveBeenCalledWith(`${ORIGIN}/m`);
    expect(await w.get("/_next/static/chunks/a.js")).toBeNull(); // caches nothing
  });

  test("nothing is registered in development; production registers with updateViaCache none", async () => {
    const register = vi.fn(async () => ({}) as ServiceWorkerRegistration);
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { register } });
    try {
      vi.stubEnv("NODE_ENV", "development");
      const dev = await import("@/lib/service-worker");
      expect(await dev.registerServiceWorker()).toBeNull();
      expect(register).not.toHaveBeenCalled();

      vi.resetModules();
      vi.stubEnv("NODE_ENV", "production");
      const prod = await import("@/lib/service-worker");
      await prod.registerServiceWorker();
      expect(register).toHaveBeenCalledWith("/sw.js", { scope: "/", updateViaCache: "none" });
    } finally {
      Reflect.deleteProperty(navigator, "serviceWorker");
    }
  });
});
