import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";

import { AccountView } from "@/components/account/account-view";
import { LoginView } from "@/components/account/login-view";
import { CONSENTS, PLACEHOLDER } from "@/components/legal/legal";
import { SiteFooter } from "@/components/site-footer";
import { RequestForm } from "@/components/request/request-form";
import { api } from "@/lib/api";
import DisclaimerPage from "@/app/disclaimer/page";
import PrivacyPage from "@/app/privacy/page";
import TermsPage from "@/app/terms/page";
import { mockApi } from "./api-mock";
import { FakeSite } from "./fake-account";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

let site: FakeSite;
let fetchMock: ReturnType<typeof mockApi>;
beforeEach(() => {
  site = new FakeSite();
  fetchMock = mockApi({}, site);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("every API call carries a new X-Request-ID", async () => {
  await api.requestConfig();
  await api.requestConfig();
  const ids = fetchMock.mock.calls.map(([, init]) => (init?.headers as Record<string, string>)["X-Request-ID"]);
  expect(ids).toHaveLength(2);
  expect(ids[0]).toMatch(/^web-[0-9a-f]{32}$/);
  expect(ids[0]).not.toBe(ids[1]);
});

test("without a Turnstile site key there is no 'I'm human' widget and no token header", async () => {
  render(<RequestForm sessionId={null} />);
  await screen.findByLabelText("Your name");
  expect(screen.queryByTestId("human-check")).toBeNull();
  await api.createRequest({} as never, undefined).catch(() => undefined); // refused: only the headers matter here
  const [, init] = fetchMock.mock.calls.at(-1)!;
  expect((init?.headers as Record<string, string>)["X-Turnstile-Token"]).toBeUndefined();
  await api.createRequest({} as never, "token-from-widget").catch(() => undefined);
  const [, withToken] = fetchMock.mock.calls.at(-1)!;
  expect((withToken?.headers as Record<string, string>)["X-Turnstile-Token"]).toBe("token-from-widget");
});

test("privacy notice: draft banner, our exact consent texts, grievance officer placeholders", () => {
  render(PrivacyPage());
  expect(screen.getByTestId("draft-banner").textContent).toContain("Draft, pending legal review");
  const consents = screen.getByTestId("consent-texts").textContent!;
  for (const c of CONSENTS) {
    expect(consents).toContain(c.text);
    expect(consents).toContain(c.version);
  }
  expect(screen.getByTestId("grievance-officer").textContent).toContain(PLACEHOLDER.grievanceName);
  expect(document.body.textContent).toContain("Data Protection Board of India");
  expect(document.body.textContent).toContain("90 days after the job is completed or cancelled");
});

test("terms and disclaimer are drafts too, and the footer links all three", () => {
  render(TermsPage());
  expect(screen.getByTestId("draft-banner")).toBeDefined();
  expect(document.body.textContent).toContain(PLACEHOLDER.company);
  cleanup();
  render(DisclaimerPage());
  expect(document.body.textContent).toContain("not a replacement for a professional inspection");
  cleanup();
  render(<SiteFooter />);
  const links = within(screen.getByRole("navigation", { name: "Legal" })).getAllByRole("link");
  expect(links.map((l) => l.getAttribute("href"))).toEqual(["/privacy", "/terms", "/disclaimer"]);
});

test("My account offers the data download", async () => {
  site.loggedIn = true;
  render(<AccountView />);
  const link = await screen.findByTestId("download-data");
  expect(link.getAttribute("href")).toBe("http://localhost:8000/api/me/export");
  expect(document.body.textContent).toContain("kept only without your name, number, address and notes");
});

test("forms with personal data post: submitted before the page's script runs, nothing lands in the URL", async () => {
  render(<RequestForm sessionId={null} />);
  await screen.findByLabelText("Your name");
  const forms = [...document.querySelectorAll("form")];
  cleanup();
  render(<LoginView />);
  await screen.findByRole("button", { name: /send/i });
  forms.push(...document.querySelectorAll("form"));
  expect(forms.length).toBeGreaterThan(1);
  for (const f of forms) expect(f.getAttribute("method")).toBe("post");
});
