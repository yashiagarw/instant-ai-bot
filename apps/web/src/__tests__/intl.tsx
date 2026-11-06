import type { ReactNode } from "react";
import { render } from "@testing-library/react";

import type { Locale } from "@/i18n/config";
import { siteMessages } from "@/i18n/messages";
import { IntlProvider } from "@/i18n/provider";

/** Render as on a /hi (or /) page: the page's provider, which also marks the language. */
export function renderIn(locale: Locale, ui: ReactNode) {
  return render(ui, {
    wrapper: ({ children }) => (
      <IntlProvider locale={locale} messages={siteMessages(locale)} page>
        {children}
      </IntlProvider>
    ),
  });
}
