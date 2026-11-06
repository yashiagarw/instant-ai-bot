"use client";

import { useLocale } from "next-intl";
import { useCallback } from "react";

import { isLocale, localeHref, type Locale } from "./config";

export function useSiteLocale(): Locale {
  const l = useLocale();
  return isLocale(l) ? l : "en";
}

/** Internal links that stay in the page's language: useLocaleHref()("/diagnose") -> "/hi/diagnose" on Hindi pages. */
export function useLocaleHref() {
  const locale = useSiteLocale();
  return useCallback((href: string) => localeHref(locale, href), [locale]);
}
