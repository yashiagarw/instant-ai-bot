"use client";

import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { createContext, useContext, useEffect, type ReactNode } from "react";

import { TIME_ZONE, type Locale } from "./config";
import { rememberLanguage } from "./preference";

const LocalePage = createContext(false);

/** True inside the pages that exist in English and Hindi (landing, diagnosis, result): the language switch shows. */
export function useIsLocalePage(): boolean {
  return useContext(LocalePage);
}

/** next-intl's provider for client components, with our time zone. `lang` on a wrapper (display: contents) marks the
 * language for screen readers and fonts; `page` also sets <html lang> and remembers the choice (notifications follow
 * it, see preference.ts). */
export function IntlProvider({
  locale,
  messages,
  page = false,
  children,
}: {
  locale: Locale;
  /** Omitted: the messages of the provider above are used (English pages: the root layout's). */
  messages?: AbstractIntlMessages;
  page?: boolean;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!page) return;
    document.documentElement.lang = locale;
    rememberLanguage(locale);
    return () => {
      document.documentElement.lang = "en";
    };
  }, [locale, page]);
  const content = page ? (
    <LocalePage.Provider value>
      <div lang={locale} className={locale === "hi" ? "hindi-page contents" : "contents"}>
        {children}
      </div>
    </LocalePage.Provider>
  ) : (
    children
  );
  if (!messages) return content;
  return (
    <NextIntlClientProvider locale={locale} messages={messages} timeZone={TIME_ZONE}>
      {content}
    </NextIntlClientProvider>
  );
}
