// Translations in Server Components (the landing page's hero and "How it works", page titles): next-intl's
// createTranslator over the same messages, from the locale in the URL. No request config is read, so the pages
// stay static.
import { createTranslator } from "next-intl";
import type { Metadata } from "next";

import { isLocale, LOCALES, localeHref, type Locale } from "./config";
import { siteMessages, type SiteMessages } from "./messages";

export async function localeOf(params: Promise<{ locale: string }>): Promise<Locale> {
  const { locale } = await params;
  return isLocale(locale) ? locale : "en";
}

export function serverT<N extends keyof SiteMessages>(locale: Locale, namespace: N) {
  return createTranslator({ locale, messages: siteMessages(locale), namespace });
}

/** Title, description and the two language versions of a page (hreflang). */
export function pageMetadata(locale: Locale, path: string, title: string, description?: string): Metadata {
  return {
    title,
    ...(description ? { description } : {}),
    alternates: {
      canonical: localeHref(locale, path),
      languages: Object.fromEntries(LOCALES.map((l) => [l === "en" ? "en-IN" : "hi-IN", localeHref(l, path)])),
    },
  };
}
