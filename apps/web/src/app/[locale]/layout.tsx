import { notFound } from "next/navigation";

import { isLocale, LOCALES } from "@/i18n/config";
import { sharedMessages } from "@/i18n/messages";
import { IntlProvider } from "@/i18n/provider";

// English (/, /diagnose…, rewritten to /en/… in next.config.ts) and Hindi (/hi, /hi/diagnose…): both prerendered.
export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

// The layout reads the language from the URL (for lang="hi", the Hindi messages and notFound()). Moving between pages
// in the same language reuses it; only entering these pages from elsewhere or switching language waits for it, and
// both languages are prerendered. So this segment may block (Next's instant-navigation validation, dev only); the
// pages below read the URL inside <Suspense> and are still validated.
export const instant = false;

export default async function LocaleLayout({ children, params }: LayoutProps<"/[locale]">) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return (
    // `common` (header, footer, stepper) here, for Hindi (English pages use the root layout's, sent once); each page
    // adds the namespaces it uses (i18n/localized.tsx).
    <IntlProvider locale={locale} messages={locale === "en" ? undefined : sharedMessages(locale)} page>
      {children}
    </IntlProvider>
  );
}
