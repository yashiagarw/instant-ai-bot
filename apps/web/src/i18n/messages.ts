import type { Locale } from "./config";
import en from "./messages/site.en.json";
import hi from "./messages/site.hi.json";

export type SiteMessages = typeof en;

// Hindi is checked key for key against English by src/__tests__/i18n.test.ts, so no message is ever missing.
const SITE: Record<Locale, SiteMessages> = { en, hi };

export function siteMessages(locale: Locale): SiteMessages {
  return SITE[locale];
}

/** Only the namespaces a page uses (plus `common`): the messages travel with every page, so each page gets its own. */
export function pageMessages<N extends keyof SiteMessages>(locale: Locale, namespaces: N[]): Pick<SiteMessages, "common" | N> {
  const all = SITE[locale];
  return Object.fromEntries(["common", ...namespaces].map((n) => [n, all[n as keyof SiteMessages]])) as Pick<
    SiteMessages,
    "common" | N
  >;
}

/** The namespaces shared components need on every page (header, footer, errors), in English: pages outside the
 * /hi routes are English only. */
export function sharedMessages(locale: Locale = "en"): Pick<SiteMessages, "common"> {
  return { common: SITE[locale].common };
}
