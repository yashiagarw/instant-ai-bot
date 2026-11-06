import { HowItWorks } from "@/components/landing/how-it-works";
import { Hero } from "@/components/landing/hero";
import { ProblemTiles } from "@/components/landing/problem-tiles";
import type { Locale } from "@/i18n/config";
import { pageMessages } from "@/i18n/messages";
import { IntlProvider } from "@/i18n/provider";

/** The landing page's content in one language (the page reads the language from the URL inside <Suspense>). */
export function Landing({ locale }: { locale: Locale }) {
  return (
    <>
      <Hero locale={locale} />
      <HowItWorks locale={locale} />
      <IntlProvider locale={locale} messages={pageMessages(locale, ["landing"])}>
        <ProblemTiles />
      </IntlProvider>
    </>
  );
}
