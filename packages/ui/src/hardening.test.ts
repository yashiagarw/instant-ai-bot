import { describe, expect, test, vi } from "vitest";

import { newRequestId, scrubEvent, scrubText, sendServerError } from "./observability";
import { contentSecurityPolicy, securityHeaders } from "./security-headers";

// The API accepts X-Request-ID only if it matches this (backend/app/observability/logs.py VALID_ID).
const API_VALID_ID = /^[A-Za-z0-9._-]{8,64}$/;

describe("request ids", () => {
  test("are new for every call and pass the API's check", () => {
    const a = newRequestId("web");
    const b = newRequestId("adm");
    expect(a).not.toBe(b);
    expect(a).toMatch(/^web-[0-9a-f]{32}$/);
    for (const id of [a, b, newRequestId("mech")]) expect(id).toMatch(API_VALID_ID);
  });
});

describe("scrubbing before Sentry", () => {
  test("masks phone numbers, emails, plates, codes and tokens", () => {
    const out = scrubText("Call 98765 43210 or +919876543210, mail asha@example.com, car DL 3C AB 1234, code 482913, token abcdefghijklmnopqrstuvwxyz0123");
    for (const secret of ["98765", "9876543210", "asha@", "1234", "482913", "abcdefghijklmnopqrstuvwxyz"]) expect(out).not.toContain(secret);
    expect(out).toContain("[PHONE]");
    expect(out).toContain("[EMAIL]");
  });

  test("drops cookies, headers, bodies, query strings and the user", () => {
    const event = scrubEvent({
      request: { url: "https://api.instantmechanic.online/api/me?phone=9876543210", cookies: { a: 1 }, headers: { Cookie: "x" }, data: "body" },
      user: { ip_address: "1.2.3.4" },
      message: "failed for 9876543210",
      exception: { values: [{ value: "Asha asha@example.com" }] },
      breadcrumbs: [{ message: "GET /api/me?x=1", data: { url: "https://x/y?phone=9876543210" } }],
    });
    const text = JSON.stringify(event);
    for (const secret of ["9876543210", "cookies", "Cookie", "1.2.3.4", "asha@", "?phone", "body"]) expect(text).not.toContain(secret);
  });

  test("server errors go to Sentry's envelope endpoint only with a DSN, scrubbed", async () => {
    const fetchMock = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    await sendServerError(undefined, new Error("x"), {});
    expect(fetchMock).not.toHaveBeenCalled();
    await sendServerError("https://abc123@o1.ingest.sentry.io/42", new Error("no row for 9876543210"), { app: "web" });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://o1.ingest.sentry.io/api/42/envelope/");
    expect(String((init.headers as Record<string, string>)["X-Sentry-Auth"])).toContain("sentry_key=abc123");
    expect(String(init.body)).not.toContain("9876543210");
    vi.unstubAllGlobals();
  });
});

describe("Content-Security-Policy", () => {
  const prod = contentSecurityPolicy({
    apiUrl: "https://api.instantmechanic.online",
    filesUrl: "https://files.instantmechanic.online",
    sentryDsn: "https://abc@o1.ingest.sentry.io/42",
    turnstile: true,
    extraImg: ["https://tiles.stadiamaps.com"],
    dev: false,
  });
  const d = Object.fromEntries(prod.split("; ").map((x) => [x.split(" ")[0], x.split(" ").slice(1)]));

  test("allows only what the apps use", () => {
    expect(d["connect-src"]).toEqual([
      "'self'",
      "https://api.instantmechanic.online",
      "https://files.instantmechanic.online",
      "https://o1.ingest.sentry.io",
      "https://challenges.cloudflare.com",
    ]);
    expect(d["img-src"]).toContain("https://tiles.stadiamaps.com");
    expect(d["script-src"]).toEqual(["'self'", "'unsafe-inline'", "https://challenges.cloudflare.com"]);
    expect(d["frame-src"]).toEqual(["https://challenges.cloudflare.com"]);
    expect(d["frame-ancestors"]).toEqual(["'none'"]);
    expect(d["object-src"]).toEqual(["'none'"]);
    expect(d["base-uri"]).toEqual(["'self'"]);
    expect(d["form-action"]).toEqual(["'self'"]);
    expect(prod).toContain("upgrade-insecure-requests");
    expect(prod).not.toContain("unsafe-eval");
  });

  test("development: eval for React's dev tools, no https upgrade; no Turnstile, no frames", () => {
    const dev = contentSecurityPolicy({ apiUrl: "http://localhost:8000", dev: true });
    expect(dev).toContain("'unsafe-eval'");
    expect(dev).not.toContain("upgrade-insecure-requests");
    expect(dev).toContain("frame-src 'none'");
  });

  test("the other headers", () => {
    const h = Object.fromEntries(securityHeaders({ dev: false, referrer: "strict-origin-when-cross-origin", camera: true }).map((x) => [x.key, x.value]));
    expect(h["X-Frame-Options"]).toBe("DENY");
    expect(h["X-Content-Type-Options"]).toBe("nosniff");
    expect(h["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(h["Permissions-Policy"]).toContain("camera=(self)");
    expect(h["Permissions-Policy"]).toContain("geolocation=()");
  });
});
