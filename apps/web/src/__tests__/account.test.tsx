import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { AccountLink } from "@/components/account/account-link";
import { AccountView } from "@/components/account/account-view";
import { LoginView, safeNext } from "@/components/account/login-view";
import { RequestDetailView } from "@/components/account/request-detail-view";
import { mockApi } from "./api-mock";
import { CODE, FakeSite, REQUEST } from "./fake-account";
import { RED_OIL_LIGHT } from "./fake-photos";

const push = vi.fn();
const replace = vi.fn();
let params: Record<string, string> = {};
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useParams: () => params,
  useSearchParams: () => search,
  useRouter: () => ({ push, replace }),
}));

let site: FakeSite;
let fetchMock: ReturnType<typeof mockApi>;

beforeEach(() => {
  site = new FakeSite();
  fetchMock = mockApi({}, site);
  push.mockReset();
  replace.mockReset();
  params = {};
  search = new URLSearchParams();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function toCodeStep() {
  render(<LoginView />);
  fireEvent.change(await screen.findByLabelText("Mobile number"), { target: { value: "98765 43210" } });
  fireEvent.click(screen.getByRole("button", { name: "Send code" }));
  return screen.findByLabelText("6-digit code");
}

test("every API call sends the login cookie (credentials: include)", async () => {
  render(<AccountLink />);
  await screen.findByText("Log in");
  expect(fetchMock.mock.calls.every(([, init]) => (init as RequestInit)?.credentials === "include")).toBe(true);
});

test("login: phone, code, consent, wrong code message, then the account", async () => {
  render(<LoginView />);
  const phone = await screen.findByLabelText("Mobile number");
  fireEvent.change(phone, { target: { value: "12345" } });
  fireEvent.click(screen.getByRole("button", { name: "Send code" }));
  expect(screen.getByRole("alert").textContent).toBe("Enter your 10-digit mobile number");

  fireEvent.change(phone, { target: { value: "98765 43210" } }); // spaces are dropped as you type
  expect((phone as HTMLInputElement).value).toBe("9876543210");
  fireEvent.click(screen.getByRole("button", { name: "Send code" }));
  const code = await screen.findByLabelText("6-digit code");
  expect(code.getAttribute("autocomplete")).toBe("one-time-code");
  expect(screen.getByText("+91******3210")).toBeDefined();
  expect(screen.getByRole("button", { name: /Send a new code in \d+s/ })).toHaveProperty("disabled", true);

  fireEvent.change(code, { target: { value: CODE } });
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));
  expect(screen.getByRole("alert").textContent).toBe("Please tick the box to agree before logging in");
  const consent = screen.getByRole("checkbox");
  expect(consent).toHaveProperty("checked", false); // never pre-ticked
  fireEvent.click(consent);

  fireEvent.change(code, { target: { value: "000000" } });
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));
  expect((await screen.findByRole("alert")).textContent).toBe("That code is not right. 4 tries left.");

  fireEvent.change(code, { target: { value: CODE } });
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/account"));
});

test("login goes back to a page on this site only", async () => {
  expect(safeNext("/requests/abc")).toBe("/requests/abc");
  expect(safeNext("https://evil.example")).toBe("/account");
  expect(safeNext("//evil.example")).toBe("/account");
  expect(safeNext(null)).toBe("/account");
  search = new URLSearchParams("next=/requests/abc");
  const code = await toCodeStep();
  fireEvent.change(code, { target: { value: CODE } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/requests/abc"));
});

test("account: logged-out visitors are sent to log in", async () => {
  render(<AccountView />);
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=/account"));
});

test("account: my garage, diagnosis history, my requests and log out", async () => {
  site.loggedIn = true;
  render(<AccountView />);
  expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("My account");
  expect(screen.getByText("+91******3210")).toBeDefined();

  const garage = screen.getByTestId("garage");
  expect(garage.textContent).toContain("Maruti Suzuki Swift · Petrol 1.2 AMT");
  fireEvent.click(within(garage).getByRole("button", { name: "Remove Maruti Suzuki Swift · Petrol 1.2 AMT" }));
  await waitFor(() => expect(screen.queryByTestId("garage")).toBeNull());
  expect(screen.getByText("Cars you diagnose while logged in are saved here.")).toBeDefined();

  const history = within(screen.getByTestId("history")).getByRole("link");
  expect(history.getAttribute("href")).toBe(`/diagnose/${site.history[0].session_id}/result`);
  expect(history.textContent).toContain("Slow/pinhole puncture");
  const request = within(screen.getByTestId("my-requests")).getByRole("link");
  expect(request.getAttribute("href")).toBe(`/requests/${REQUEST.id}`);
  expect(request.textContent).toContain("IM-7K3Q9P");
  expect(request.textContent).toContain("We called you");

  fireEvent.click(screen.getByRole("button", { name: "Log out" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  expect(site.loggedIn).toBe(false);
});

test("account deletion needs DELETE typed, then confirms", async () => {
  site.loggedIn = true;
  render(<AccountView />);
  fireEvent.click(await screen.findByRole("button", { name: "Delete my account" }));
  const submit = screen.getByRole("button", { name: "Delete everything" });
  expect(submit).toHaveProperty("disabled", true);
  fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: "delete" } });
  expect(submit).toHaveProperty("disabled", true);
  fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: "DELETE" } });
  fireEvent.click(submit);
  expect(await screen.findByText("Your account is deleted")).toBeDefined();
  expect(site.deleted).toBe(true);
});

test("request page: the status timeline, and someone else's request is not found", async () => {
  site.loggedIn = true;
  params = { id: REQUEST.id };
  render(<RequestDetailView />);
  expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("IM-7K3Q9P");
  expect(screen.getByText("Status: We called you")).toBeDefined();
  const steps = within(screen.getByTestId("timeline")).getAllByRole("listitem");
  expect(steps.map((s) => s.textContent)).toEqual([
    "Request receivedDone · 30 Oct 2026",
    "Picked up by our teamDone",
    "We called youNow",
    "Mechanic assignedNext",
    "CompletedNext",
  ]);
  expect(steps[2].getAttribute("aria-current")).toBe("step");
  cleanup();
  params = { id: "00000000-0000-4000-8000-000000000099" };
  render(<RequestDetailView />);
  expect(await screen.findByText(/couldn't find that/i)).toBeDefined();
});

test("request page shows the customer's photos with what they may show, and red-light safety", async () => {
  site.loggedIn = true;
  params = { id: REQUEST.id };
  const photo = { id: "p1", status: "ready", width: 4, height: 3, url: "https://storage.test/p1.jpg?sig=x", expires_in: 300 };
  mockApi(
    { "/api/uploads": (u: URL) => (u.searchParams.get("session_id") === REQUEST.session_id ? [{ ...photo, findings: [RED_OIL_LIGHT("p1", "warning_light")] }] : "missing") },
    site,
  );
  render(<RequestDetailView />);
  const gallery = await screen.findByTestId("photo-gallery");
  expect(within(gallery).getByRole("img", { name: "Your photo 1" })).toBeDefined();
  expect(within(gallery).getByText(/Possible: Engine oil pressure light/)).toBeDefined();
  expect(screen.getByTestId("safety-banner").textContent).toMatch(/Stop now/);
});

test("request page sends logged-out visitors to log in and back", async () => {
  params = { id: REQUEST.id };
  render(<RequestDetailView />);
  await waitFor(() => expect(replace).toHaveBeenCalledWith(`/login?next=/requests/${REQUEST.id}`));
});

test("the header shows Log in, or My account once logged in", async () => {
  render(<AccountLink />);
  expect((await screen.findByTestId("account-link")).getAttribute("href")).toBe("/login");
  cleanup();
  site.loggedIn = true;
  render(<AccountLink />);
  await waitFor(() => expect(screen.getByTestId("account-link").textContent).toBe("My account"));
  expect(screen.getByTestId("account-link").getAttribute("href")).toBe("/account");
});
