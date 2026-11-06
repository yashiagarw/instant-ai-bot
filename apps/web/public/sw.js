// The site's one service worker (scope "/"), registered by the customer "Turn on alerts" card and by the mechanic
// app (/m). Two jobs:
// 1. Alerts (web push): shows one notification per message from the server (backend/app/notify/push.py:
//    {title, body, url, tag}) and opens our own site when it is tapped.
// 2. Offline shell for the mechanic app: pages under /m are network-first and kept for when the phone has no signal
//    (slow 4G), with /m/offline.html as the last resort; built JS/CSS (/_next/static, immutable) and the icons are
//    cache-first. Nothing else is cached: API calls go to the API's own address and are never stored, so no
//    customer or job data stays on the phone.

const SHELL = "im-m-shell-v1";
const STATIC = "im-static-v1";
const OFFLINE = "/m/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) => cache.addAll([OFFLINE, "/icons/mechanic-192.png"]))
      .catch(() => undefined) // installing must not fail on a bad connection
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL && k !== STATIC).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function isMechanicPage(url) {
  return url.pathname === "/m" || url.pathname.startsWith("/m/");
}

async function networkFirst(request, url) {
  const cache = await caches.open(SHELL);
  const key = url.origin + url.pathname; // one copy per page, whatever the query
  try {
    const response = await fetch(request);
    if (response.ok && response.type === "basic") cache.put(key, response.clone());
    return response;
  } catch {
    return (
      (await cache.match(key)) || (await cache.match(url.origin + "/m")) || (await cache.match(OFFLINE)) || Response.error()
    );
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(STATIC);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok && response.type === "basic") cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // the API and anything else: straight to the network
  if (request.mode === "navigate" && isMechanicPage(url)) {
    event.respondWith(networkFirst(request, url));
  } else if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(cacheFirst(request));
  }
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Instant Mechanic", {
      body: data.body || "",
      tag: data.tag || undefined, // one notification per request: a newer update replaces the older one
      renotify: Boolean(data.tag),
      icon: "/icons/icon-192.png",
      data: { url: data.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  let target = new URL("/", self.location.origin);
  try {
    const url = new URL(event.notification.data?.url || "/", self.location.origin);
    if (url.origin === self.location.origin) target = url; // never open another site
  } catch {
    // keep the home page
  }
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const w of windows) {
        if (w.url === target.href && "focus" in w) return w.focus();
      }
      return self.clients.openWindow(target.href);
    }),
  );
});
