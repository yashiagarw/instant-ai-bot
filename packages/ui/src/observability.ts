// Request ids and error reporting for the web and admin apps (Phase 5.4).
//
// - Every API call sends X-Request-ID (a new id per call); the API logs it, returns it and hands it to the worker's
//   jobs, so one id follows a request across web, API and worker. The last id is remembered and tagged on errors.
// - Sentry runs only when NEXT_PUBLIC_SENTRY_DSN is set (loaded on demand: nothing is downloaded otherwise). No
//   session replay, no default personal data; before anything is sent, phone numbers, emails, number plates, 6-digit
//   codes and tokens are masked, query strings and cookies dropped (the same rules as the API).

const PHONE = /(?<![\w+])(?:\+?91[\s.-]*|0)?[6-9](?:[\s.-]*\d){9}(?!\d)|(?<!\d)\+?\d(?:[\s.-]*\d){9,12}(?!\d)/g;
const EMAIL = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g;
const PLATE = /\b(?:[A-Z]{2}[\s.-]?\d{1,2}[\s.-]?(?:[A-Z]{1,3}[\s.-]?){0,2}\d{4}|\d{2}[\s.-]?BH[\s.-]?\d{4}[\s.-]?[A-Z]{1,2})\b/gi;
const CODE = /(?<!\d)\d{6}(?!\d)/g;
const TOKEN = /\b[A-Za-z0-9_-]{24,}\b/g;

let lastRequestId: string | null = null;

export function newRequestId(prefix: "web" | "adm" | "mech"): string {
  const raw =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "")
      : Math.random().toString(16).slice(2) + Date.now().toString(16);
  lastRequestId = `${prefix}-${raw.slice(0, 32)}`;
  return lastRequestId;
}

export function scrubText(text: string): string {
  return text
    .replace(EMAIL, "[EMAIL]")
    .replace(PLATE, "[VEHICLE_NUMBER]")
    .replace(PHONE, "[PHONE]")
    .replace(CODE, "[code]")
    .replace(TOKEN, "[token]");
}

type Json = Record<string, unknown>;

function scrubValue(v: unknown): unknown {
  if (typeof v === "string") return scrubText(v);
  if (Array.isArray(v)) return v.map(scrubValue);
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v as Json).map(([k, x]) => [k, scrubValue(x)]));
  return v;
}

/** A Sentry event without personal data (also used for breadcrumbs). */
export function scrubEvent<T extends Json>(event: T): T {
  const e = event as Json;
  const req = e.request as Json | undefined;
  if (req) {
    for (const k of ["cookies", "headers", "data", "query_string", "env"]) delete req[k];
    if (typeof req.url === "string") req.url = req.url.split("?")[0];
  }
  delete e.user;
  if (typeof e.message === "string") e.message = scrubText(e.message);
  const exc = e.exception as { values?: Json[] } | undefined;
  for (const v of exc?.values ?? []) {
    if (typeof v.value === "string") v.value = scrubText(v.value);
  }
  const crumbs = (e.breadcrumbs as Json[] | undefined) ?? [];
  e.breadcrumbs = crumbs.map(scrubBreadcrumb);
  if (e.extra) e.extra = scrubValue(e.extra);
  e.tags = { ...((e.tags as Json) ?? {}), ...(lastRequestId ? { request_id: lastRequestId } : {}) };
  return event;
}

export function scrubBreadcrumb<T extends Json>(crumb: T): T {
  const c = crumb as Json;
  if (typeof c.message === "string") c.message = scrubText(c.message);
  if (c.data && typeof c.data === "object") {
    const data = { ...(c.data as Json) };
    if (typeof data.url === "string") data.url = data.url.split("?")[0];
    c.data = scrubValue(data);
  }
  return crumb;
}

let started = false;

/** Start Sentry in the browser when a DSN is configured. Safe to call more than once. */
export function startErrorReporting(dsn: string | undefined, app: "web" | "admin", environment?: string): void {
  if (!dsn || started || typeof window === "undefined") return;
  started = true;
  void import("@sentry/browser")
    .then((Sentry) => {
      Sentry.init({
        dsn,
        environment,
        // Sentry 11 collects user info, cookies, headers, bodies and query strings by default: none of it here.
        dataCollection: {
          userInfo: false,
          cookies: false,
          httpHeaders: false,
          httpBodies: [],
          urlQueryParams: false,
        },
        tracesSampleRate: 0,
        // No session replay and no screenshots: only errors.
        beforeSend: (event) => scrubEvent(event as unknown as Json) as unknown as typeof event,
        beforeBreadcrumb: (crumb) => scrubBreadcrumb(crumb as unknown as Json) as unknown as typeof crumb,
        initialScope: { tags: { app } },
      });
    })
    .catch(() => {
      started = false; // blocked or offline: try again on the next page
    });
}

/**
 * Server side (the Next.js server's onRequestError): one error to Sentry as an "envelope", with plain fetch: no SDK
 * and no tracing libraries in the server bundle. Scrubbed like everything else; nothing sent without a DSN.
 * https://develop.sentry.dev/sdk/data-model/envelopes/
 */
export async function sendServerError(
  dsn: string | undefined,
  error: unknown,
  tags: Record<string, string>,
  environment?: string,
): Promise<void> {
  if (!dsn) return;
  let url: URL;
  try {
    url = new URL(dsn);
  } catch {
    return;
  }
  const project = url.pathname.replace(/^\//, "");
  const key = url.username;
  const err = error instanceof Error ? error : new Error(String(error));
  const eventId = (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : Date.now().toString(16)).replace(/-/g, "");
  const event = scrubEvent({
    event_id: eventId,
    timestamp: Date.now() / 1000,
    level: "error",
    platform: "node",
    environment,
    tags,
    exception: { values: [{ type: err.name, value: err.message }] },
  } as Record<string, unknown>);
  const body = [JSON.stringify({ event_id: eventId, dsn }), JSON.stringify({ type: "event" }), JSON.stringify(event)].join("\n");
  try {
    await fetch(`${url.protocol}//${url.host}/api/${project}/envelope/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-sentry-envelope",
        "X-Sentry-Auth": `Sentry sentry_version=7, sentry_key=${key}, sentry_client=im-next/1.0`,
      },
      body,
    });
  } catch {
    // Sentry unreachable: the JSON log line is still written
  }
}
