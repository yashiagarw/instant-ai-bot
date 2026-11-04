// Instant Mechanic alerts (web push). Shows one notification per message from the server
// (backend/app/notify/push.py: {title, body, url, tag}) and opens our own site when it is tapped.
// Registered by the "Turn on alerts" button (src/components/notify/alerts-button.tsx). No caching, no offline mode.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

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
      icon: "/favicon.ico",
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
