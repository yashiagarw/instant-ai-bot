"use client";

import { useTranslations } from "next-intl";
import { useSyncExternalStore } from "react";
import { Languages } from "lucide-react";

import { localeHref, splitLocale } from "@/i18n/config";
import { useSiteLocale } from "@/i18n/navigation";
import { rememberLanguage } from "@/i18n/preference";
import { useIsLocalePage } from "@/i18n/provider";

const noop = () => () => undefined;

/** English <-> हिन्दी on the pages that exist in both (landing, diagnosis, result). Keeps the page, ?topic= / ?step=
 * and #how-it-works. The choice is remembered for notifications (i18n/preference.ts). A plain link that works before
 * JavaScript loads; the address is read in the browser (no usePathname: the pages stay prerendered). */
export function LanguageSwitch() {
  const t = useTranslations("common");
  const locale = useSiteLocale();
  const page = useIsLocalePage();
  // The page's address in the browser; "/" while prerendering (the link then goes to the other language's home).
  const here = useSyncExternalStore(
    noop,
    () => window.location.pathname + window.location.search + window.location.hash,
    () => "/",
  );
  if (!page) return null;
  const other = locale === "hi" ? "en" : "hi";
  const { path } = splitLocale(here.replace(/[?#].*$/, ""));
  const href = localeHref(other, path) + (here.match(/[?#].*$/)?.[0] ?? "");
  return (
    <a
      href={href}
      hrefLang={other}
      lang={other}
      aria-label={t("switchLanguageLabel")}
      data-testid="language-switch"
      onClick={() => rememberLanguage(other)}
      className="inline-flex min-h-11 items-center gap-1.5 rounded-full border-2 border-ink/15 bg-white px-3 font-bold text-ink outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring"
    >
      <Languages aria-hidden="true" className="size-5 text-orange-text" />
      {t("switchLanguage")}
    </a>
  );
}
