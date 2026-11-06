// Every component test renders inside the site's providers (Phase 5.5): English messages (next-intl).
// A test can pass its own `wrapper` (e.g. Hindi: renderIn("hi", ...) from ./intl).
import { vi } from "vitest";
import type { ReactNode } from "react";

import { siteMessages } from "@/i18n/messages";
import { IntlProvider } from "@/i18n/provider";

export function EnglishProviders({ children }: { children: ReactNode }) {
  return (
    <IntlProvider locale="en" messages={siteMessages("en")}>
      {children}
    </IntlProvider>
  );
}

vi.mock("@testing-library/react", async (importOriginal) => {
  const rtl = await importOriginal<typeof import("@testing-library/react")>();
  return {
    ...rtl,
    render: ((ui: Parameters<typeof rtl.render>[0], options?: Parameters<typeof rtl.render>[1]) =>
      rtl.render(ui, { wrapper: EnglishProviders, ...options })) as typeof rtl.render,
  };
});
