// Phase 5.5: the Hindi pages. UI text in Hindi; fault names only from reviewed Hindi; safety text in English.
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";

import { Landing } from "@/components/landing/landing";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { ResultView } from "@/components/result/result-view";
import { mockApi } from "./api-mock";
import { FakeDiagnosis } from "./fake-diagnosis";
import { renderIn } from "./intl";

let sessionId = "";
vi.mock("next/navigation", () => ({
  useParams: () => ({ sessionId }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

/** The landing page as the route renders it: header, content, footer. */
function Home({ locale }: { locale: "en" | "hi" }) {
  return (
    <>
      <SiteHeader />
      <Landing locale={locale} />
      <SiteFooter />
    </>
  );
}

let fake: FakeDiagnosis;
beforeEach(() => {
  fake = new FakeDiagnosis();
  mockApi({}, fake);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.lang = "en";
});

test("Hindi landing page: Hindi heading and CTA to /hi/diagnose, html lang, switch back to English", async () => {
  renderIn("hi", <Home locale="hi" />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("जानिए आपकी कार में क्या खराबी है");
  expect(screen.getByRole("link", { name: /मुफ़्त जाँच शुरू करें/ }).getAttribute("href")).toBe("/hi/diagnose");
  expect(document.documentElement.lang).toBe("hi");
  const sw = screen.getByTestId("language-switch");
  expect(sw.getAttribute("href")).toBe("/"); // jsdom's address is "/": the English home
  expect(sw.getAttribute("lang")).toBe("en");
  expect(localStorage.getItem("im.lang")).toBe("hi"); // notifications follow it
  expect(screen.getByText(/ये किसी मैकेनिक की पेशेवर जाँच की जगह नहीं ले सकते/)).toBeDefined(); // disclaimer
});

test("English landing page offers हिन्दी; pages outside the two-language routes have no switch", async () => {
  const home = <Home locale="en" />;
  renderIn("en", home);
  expect(screen.getByTestId("language-switch").getAttribute("href")).toBe("/hi");
  cleanup();
  render(home); // root provider only, as on /account or /request
  expect(screen.queryByTestId("language-switch")).toBeNull();
});

function finished(body: Record<string, unknown>) {
  const r = fake.handle("POST", "/api/diagnosis/sessions", body)!;
  sessionId = (r.json as { session_id: string }).session_id;
}

test("Hindi result: reviewed Hindi fault name when there is one, English (lang=en) otherwise; safety stays English", async () => {
  finished({ vehicle: { variant_id: 16 }, text: "smoke from the bonnet" });
  const original = fake.handle.bind(fake);
  fake.handle = (method, p, b) => {
    const out = original(method, p, b);
    if (out && method === "GET" && p.endsWith("/result")) {
      const r = out.json as { ranked: { name_hi?: string | null }[] };
      r.ranked = r.ranked.map((f, i) => ({ ...f, name_hi: i === 0 ? "टायर पंक्चर" : null }));
    }
    return out;
  };
  renderIn("hi", <ResultView />);
  const heading = await screen.findByRole("heading", { level: 1, name: "आपका नतीजा" });
  expect(heading).toBeDefined();
  const banner = screen.getByTestId("safety-banner");
  expect(banner.getAttribute("lang")).toBe("en");
  expect(banner.textContent).toMatch(/Safety/);
  const top = screen.queryByRole("article");
  if (top) {
    const name = within(top).getByRole("heading", { level: 2 });
    expect(name.textContent).toBe("टायर पंक्चर");
    expect(name.getAttribute("lang")).toBe("hi");
  }
  expect(screen.getByTestId("disclaimer").textContent).toContain("अनुमान");
  expect(screen.getByTestId("coverage").textContent).toMatch(/सेगमेंट अनुमान|सामान्य सलाह|पार्ट फ़िट/);
});
