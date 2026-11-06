import type { ReactNode } from "react";

import { isLocale } from "./config";
import { pageMessages, type SiteMessages } from "./messages";
import { IntlProvider } from "./provider";

/** The messages one page needs, in the language of its URL. An async Server Component, so pages whose other params
 * are only known at request time (the session id) can put it inside their Suspense boundary. */
export async function Localized({
  params,
  namespaces,
  children,
}: {
  params: Promise<{ locale: string }>;
  namespaces: (keyof SiteMessages)[];
  children: ReactNode;
}) {
  const { locale } = await params;
  const l = isLocale(locale) ? locale : "en";
  return (
    <IntlProvider locale={l} messages={pageMessages(l, namespaces)}>
      {children}
    </IntlProvider>
  );
}
