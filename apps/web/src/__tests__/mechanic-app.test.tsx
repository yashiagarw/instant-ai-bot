import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { JobView } from "@/components/m/job-view";
import { MechanicLoginView } from "@/components/m/login-view";
import { OffersView } from "@/components/m/offers-view";
import { ProfileView } from "@/components/m/profile-view";
import { MechanicShell } from "@/components/m/shell";
import { TodayView } from "@/components/m/today-view";
import { TrackingView } from "@/components/track/tracking-view";
import { mockApi } from "./api-mock";
import { CODE, FakeMechanic, REQUEST_ID } from "./fake-mechanic";

const push = vi.fn();
const replace = vi.fn();
let params: Record<string, string> = {};
let path = "/m";
vi.mock("next/navigation", () => ({
  useParams: () => params,
  usePathname: () => path,
  useRouter: () => ({ push, replace }),
}));

let api: FakeMechanic;

beforeEach(() => {
  api = new FakeMechanic();
  mockApi({}, api);
  push.mockReset();
  replace.mockReset();
  params = {};
  path = "/m";
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function app(view: React.ReactNode) {
  return render(<MechanicShell>{view}</MechanicShell>);
}

test("sign in: Hindi first, the code, a wrong code message, then the app", async () => {
  render(<MechanicLoginView />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("साइन इन करें");
  fireEvent.change(screen.getByLabelText("मोबाइल नंबर"), { target: { value: "12345" } });
  fireEvent.click(screen.getByRole("button", { name: "कोड भेजें" }));
  expect((await screen.findByRole("alert")).textContent).toBe("10 अंकों का मोबाइल नंबर डालें");
  fireEvent.change(screen.getByLabelText("मोबाइल नंबर"), { target: { value: "90000 00011" } });
  fireEvent.click(screen.getByRole("button", { name: "कोड भेजें" }));
  const code = await screen.findByLabelText("6 अंकों का कोड");
  expect(screen.getByText("+91******0011")).toBeDefined();
  fireEvent.change(code, { target: { value: "000000" } });
  fireEvent.click(screen.getByRole("button", { name: "साइन इन" }));
  expect((await screen.findByRole("alert")).textContent).toBe("That code is not right. 4 tries left.");
  fireEvent.change(code, { target: { value: CODE } });
  fireEvent.click(screen.getByRole("button", { name: "साइन इन" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/m"));
});

test("signed out: the app sends them to sign in", async () => {
  app(<TodayView />);
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/m/login"));
});

test("today: on / off duty, the new offer, big tabs", async () => {
  api.signedIn = true;
  app(<TodayView />);
  expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("नमस्ते, Ravi");
  expect(screen.getByTestId("duty-pill").textContent).toBe("ड्यूटी पर");
  expect(screen.getByTestId("offers-link").getAttribute("href")).toBe("/m/offers");
  fireEvent.click(screen.getByRole("switch", { name: "ड्यूटी बंद करें" }));
  await waitFor(() => expect(screen.getByTestId("duty-pill").textContent).toBe("ड्यूटी बंद"));
  expect(api.onDuty).toBe(false);
  const tabs = within(screen.getByRole("navigation")).getAllByRole("link");
  expect(tabs.map((t) => t.getAttribute("href"))).toEqual(["/m", "/m/offers", "/m/profile"]);
  expect(tabs[0].getAttribute("aria-current")).toBe("page");
});

test("offers: approximate area only and the seconds left; accepting opens the job", async () => {
  api.signedIn = true;
  path = "/m/offers";
  app(<OffersView />);
  const offer = await screen.findByTestId("offer");
  expect(offer.textContent).toContain("Delhi, pincode 110017");
  expect(offer.textContent).toContain("लगभग 4 किमी");
  expect(offer.textContent).toContain("Weak battery");
  expect(offer.textContent).toMatch(/17\d सेकंड बचे/);
  expect(offer.textContent).toContain("पूरा पता काम लेने के बाद दिखेगा।");
  for (const secret of ["B-12", "Asha", "1234", "maps"]) expect(offer.textContent).not.toContain(secret);
  fireEvent.click(within(offer).getByRole("button", { name: "काम लें" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/m/jobs/41"));
  expect(api.offerStatus).toBe("accepted");
});

test("an offer that closed meanwhile says so", async () => {
  api.signedIn = true;
  app(<OffersView />);
  const offer = await screen.findByTestId("offer");
  api.offerStatus = "expired";
  fireEvent.click(within(offer).getByRole("button", { name: "मना करें" }));
  expect((await screen.findByRole("alert")).textContent).toBe("यह ऑफ़र अब खुला नहीं है।");
  await waitFor(() => expect(screen.queryByTestId("offer")).toBeNull());
});

test("job: address, map, masked number and call after accepting; steps in order; the fault at the end", async () => {
  api.signedIn = true;
  api.offerStatus = "accepted";
  api.requestStatus = "accepted";
  params = { id: "41" };
  app(<JobView />);
  expect((await screen.findByTestId("job-address")).textContent).toBe("B-12, 2nd floor, Malviya Nagar, 110017");
  expect(screen.getByRole("link", { name: "मैप में खोलें" }).getAttribute("href")).toContain("google.com/maps");
  expect(screen.getByTestId("job-phone").textContent).toBe("+91******1234");
  fireEvent.click(screen.getByRole("button", { name: "ग्राहक को कॉल करें" }));
  expect((await screen.findByRole("status")).textContent).toContain("आपके फ़ोन पर कॉल आ रही है");
  expect(api.calls).toEqual(["mechanic_to_customer"]);

  fireEvent.click(screen.getByRole("button", { name: "20 मिनट" }));
  expect((await screen.findByRole("status")).textContent).toBe("ग्राहक को बता दिया: लगभग 20 मिनट");
  fireEvent.click(screen.getByRole("button", { name: "निकल रहा हूँ" }));
  await waitFor(() => expect(screen.getByTestId("job-status").textContent).toBe("रास्ते में"));
  fireEvent.click(screen.getByRole("button", { name: "पहुँच गया" }));
  await waitFor(() => expect(screen.getByTestId("job-status").textContent).toBe("पहुँच गए"));
  fireEvent.click(screen.getByRole("button", { name: "काम शुरू" }));

  const choices = await screen.findByTestId("fault-choices");
  await waitFor(() => expect(within(choices).getAllByRole("radio").length).toBe(3));
  expect(choices.textContent).toContain("बैटरी कमज़ोर है");
  expect(choices.textContent).toContain("AI का अंदाज़ा #1");
  fireEvent.click(screen.getByRole("button", { name: "पूरा करें और भेजें" }));
  expect((await screen.findByRole("alert")).textContent).toContain("खराबी चुनें");
  fireEvent.click(within(choices).getByRole("radio", { name: /दूसरी \/ पक्का नहीं/ }));
  fireEvent.click(screen.getByRole("button", { name: "पूरा करें और भेजें" }));
  expect((await screen.findByRole("alert")).textContent).toContain("खराबी चुनें"); // other needs a note
  fireEvent.change(screen.getByLabelText("क्या मिला? छोटा नोट लिखें"), { target: { value: "loose earth wire" } });
  fireEvent.click(screen.getByRole("button", { name: "पूरा करें और भेजें" }));
  expect((await screen.findByRole("status")).textContent).toContain("काम पूरा हुआ");
  expect(api.outcome).toMatchObject({ status: "completed", confirmed_fault_key: "other", other_text: "loose earth wire" });
});

test("the fault picker searches Hindi and English", async () => {
  api.signedIn = true;
  api.offerStatus = "accepted";
  api.requestStatus = "in_progress";
  params = { id: "41" };
  app(<JobView />);
  const search = await screen.findByLabelText("खराबी खोजें (हिंदी या English)");
  fireEvent.change(search, { target: { value: "terminal" } });
  await waitFor(() => expect(within(screen.getByTestId("fault-choices")).getAllByRole("radio").length).toBe(2));
  fireEvent.click(screen.getByRole("radio", { name: /battery ka terminal dheela/ }));
  fireEvent.click(screen.getByRole("button", { name: "पूरा करें और भेजें" }));
  await waitFor(() => expect(api.outcome).toMatchObject({ confirmed_fault_key: "F08-BT-04", other_text: "" }));
});

test("profile: switch to English, remembered", async () => {
  api.signedIn = true;
  path = "/m/profile";
  app(<ProfileView />);
  fireEvent.click(await screen.findByRole("radio", { name: "English" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "Language" })).toBeDefined());
  expect(screen.getByTestId("duty-pill").textContent).toBe("On duty");
  expect(localStorage.getItem("im_m_lang")).toBe("en");
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/m/login"));
});

test("customer tracking updates by itself: the mechanic, the ETA, and a masked call", async () => {
  params = { id: REQUEST_ID };
  render(<TrackingView />);
  expect((await screen.findByTestId("track-status")).textContent).toBe("Finding a mechanic for you");
  expect(screen.queryByTestId("track-mechanic")).toBeNull();
  expect(screen.queryByRole("button", { name: /Call/ })).toBeNull();
  api.offerStatus = "accepted";
  api.requestStatus = "en_route";
  api.etaMinutes = 15;
  await act(() => new Promise((r) => setTimeout(r, 1200))); // the fake asks to poll every second
  await waitFor(() => expect(screen.getByTestId("track-status").textContent).toBe("Mechanic on the way"));
  expect(screen.getByTestId("track-mechanic").textContent).toContain("Ravi");
  expect(screen.getByTestId("track-eta").textContent).toBe("Arriving in about 15 minutes");
  expect(document.body.textContent).not.toMatch(/\bkm\b/);
  fireEvent.click(screen.getByRole("button", { name: "Call Ravi" }));
  expect((await screen.findByText(/We are calling your phone now/)).textContent).toBeTruthy();
  expect(api.calls).toEqual(["customer_to_mechanic"]);
});
