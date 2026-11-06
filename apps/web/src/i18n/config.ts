// Languages of the customer site (Phase 5.5): English at the usual addresses, Hindi under /hi for the landing page,
// the diagnosis and the result (/hi, /hi/diagnose, /hi/diagnose/{id}/result). English URLs are rewritten to
// /en/... inside the app (next.config.ts), so they did not change. Other pages are English only for now.
// The mechanic app (/m) uses the same messages format and provider with its own switch (components/m/i18n.tsx).

export const LOCALES = ["en", "hi"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const TIME_ZONE = "Asia/Kolkata";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** Paths that exist in both languages (everything else is English only). */
const LOCALIZED = /^\/(diagnose(\/.*)?)?$/;

/** The path without a /hi prefix, and its language. */
export function splitLocale(pathname: string): { locale: Locale; path: string } {
  const m = /^\/(hi|en)(\/.*)?$/.exec(pathname);
  if (m) return { locale: m[1] as Locale, path: m[2] || "/" };
  return { locale: DEFAULT_LOCALE, path: pathname || "/" };
}

export function isLocalized(path: string): boolean {
  return LOCALIZED.test(path.split(/[?#]/)[0]);
}

/** An internal link in the given language: "/diagnose?topic=ac" -> "/hi/diagnose?topic=ac" for Hindi. Paths that are
 * English only stay as they are. */
export function localeHref(locale: Locale, href: string): string {
  if (locale === DEFAULT_LOCALE || !href.startsWith("/") || !isLocalized(href)) return href;
  return href === "/" ? "/hi" : href.startsWith("/?") || href.startsWith("/#") ? `/hi${href.slice(1)}` : `/hi${href}`;
}
