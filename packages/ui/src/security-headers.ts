// Security headers for the web and admin apps (Phase 5.4), built at build time from the same values the app uses
// (next.config.ts). The Content-Security-Policy allows only what each app loads:
//   our own files; the API (NEXT_PUBLIC_API_URL); the photo storage (NEXT_PUBLIC_FILES_URL: SeaweedFS behind Caddy,
//   or a cloud bucket) for uploads and signed photo links; Sentry's ingest host (from NEXT_PUBLIC_SENTRY_DSN) when
//   it is on; Cloudflare Turnstile (web); the map tile host (admin, src/lib/map-tiles.ts).
// Web push needs no CSP entry (the browser talks to its push service itself; the service worker is our own file).
//
// Scripts: 'self' plus 'unsafe-inline', as Next.js documents for apps without nonces. Nonces would force every page
// to be rendered per request (no static pages, slower on 4G); the apps never render HTML from data
// (no dangerouslySetInnerHTML), and everything else is locked: no other script hosts, no plugins, no <base>, forms
// only to us, and no one may frame us.

export interface CspOptions {
  apiUrl?: string;
  filesUrl?: string;
  sentryDsn?: string;
  extraImg?: string[];
  turnstile?: boolean;
  dev: boolean;
}

export function origin(url: string | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url.replace(/[{}]/g, "")).origin;
  } catch {
    return null;
  }
}

const TURNSTILE = "https://challenges.cloudflare.com";

export function contentSecurityPolicy(o: CspOptions): string {
  const api = origin(o.apiUrl);
  const files = origin(o.filesUrl);
  const sentry = origin(o.sentryDsn);
  const list = (...xs: (string | null | false | undefined)[]) => [...new Set(xs.filter(Boolean))].join(" ");
  const https = !!api && api.startsWith("https://");
  const directives = [
    `default-src 'self'`,
    `script-src ${list("'self'", "'unsafe-inline'", o.dev && "'unsafe-eval'", o.turnstile && TURNSTILE)}`,
    `style-src 'self' 'unsafe-inline'`,
    `img-src ${list("'self'", "data:", "blob:", api, files, ...(o.extraImg ?? []))}`,
    `font-src 'self'`,
    `connect-src ${list("'self'", api, files, sentry, o.turnstile && TURNSTILE)}`,
    `frame-src ${o.turnstile ? TURNSTILE : "'none'"}`,
    `worker-src 'self'`,
    `manifest-src 'self'`,
    `object-src 'none'`,
    `base-uri 'self'`,
    `form-action 'self'`,
    `frame-ancestors 'none'`,
    https && "upgrade-insecure-requests",
  ];
  return directives.filter(Boolean).join("; ");
}

export function securityHeaders(o: CspOptions & { referrer: string; camera?: boolean }) {
  return [
    { key: "Content-Security-Policy", value: contentSecurityPolicy(o) },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: o.referrer },
    { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
    {
      key: "Permissions-Policy",
      // The photo step uses the camera through a file input; nothing uses the microphone, location or payments.
      value: `camera=${o.camera ? "(self)" : "()"}, microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()`,
    },
  ];
}
