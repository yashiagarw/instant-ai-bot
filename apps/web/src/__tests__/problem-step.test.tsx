import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { ProblemStep } from "@/components/diagnose/problem-step";
import type { VehicleChoice } from "@/lib/vehicle";
import { mockApi } from "./api-mock";
import { FakeDiagnosis } from "./fake-diagnosis";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

const SWIFT: VehicleChoice = { kind: "listed", variant_id: 16, label: "Maruti Suzuki Swift", price_segment: "budget" };
const EV: VehicleChoice = {
  kind: "unlisted",
  label: "Tata Nexon EV 2022",
  unlisted: { make: "Tata", model: "Nexon EV", year: 2022, fuel: "ev", transmission: "at", price_segment: null },
};

beforeEach(() => push.mockReset());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("tiles show English and Hindi labels, Beta for untuned ones, and are filtered for the car", async () => {
  const fetchMock = mockApi();
  render(<ProblemStep vehicle={SWIFT} />);
  const tyres = await screen.findByRole("button", { name: /Tyres/ });
  expect(tyres.textContent).toContain("टायर");
  expect(within(tyres).queryByText("Beta")).toBeNull();
  expect(screen.queryByRole("button", { name: /EV & hybrid/ })).toBeNull(); // petrol car
  const calls = fetchMock.mock.calls.map((c) => String(c[0]));
  expect(calls.some((u) => u.endsWith("/api/categories?variant_id=16"))).toBe(true);

  const emergency = within(screen.getByRole("heading", { name: "Emergency help" }).closest("section")!);
  const labels = emergency.getAllByRole("button").map((b) => b.textContent?.replace(/Beta.*/, ""));
  expect(labels).toEqual([
    "Battery dead",
    "Flat tyre",
    "Petrol finished",
    "Locked out",
    "Car stuck",
    "Car in water",
    "Accident / tow",
    "Smoke or burning smell",
  ]);
  expect(within(emergency.getByRole("button", { name: /Locked out/ })).getByText("Beta")).toBeDefined();
});

test("on an EV, Petrol finished becomes Battery ran out", async () => {
  const fetchMock = mockApi();
  render(<ProblemStep vehicle={EV} />);
  expect(await screen.findByRole("button", { name: /Battery ran out/ })).toBeDefined();
  expect(screen.queryByRole("button", { name: /Petrol finished/ })).toBeNull();
  expect(String(fetchMock.mock.calls[0][0])).toContain("fuel=ev&transmission=at");
});

test("a tile starts a session for the car and opens the questions", async () => {
  const fake = new FakeDiagnosis();
  mockApi({}, fake);
  render(<ProblemStep vehicle={SWIFT} />);
  fireEvent.click(await screen.findByRole("button", { name: /Tyres/ }));
  await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
  const [id] = [...fake.sessions.keys()];
  expect(push).toHaveBeenCalledWith(`/diagnose/${id}`);
  expect(fake.sessions.get(id)!.topic).toBe("Tyres");
});

test("free text needs a few words, then starts a session without a topic", async () => {
  const fake = new FakeDiagnosis();
  mockApi({}, fake);
  render(<ProblemStep vehicle={EV} />);
  await screen.findByRole("button", { name: /Tyres/ });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(screen.getByText(/Tell us a little about the problem/)).toBeDefined();
  fireEvent.change(screen.getByLabelText("Describe what's happening"), { target: { value: "gaadi se smoke aa raha" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await waitFor(() => expect(push).toHaveBeenCalled());
  const s = [...fake.sessions.values()][0];
  expect(s.topic).toBeNull();
  expect(s.vehicle).toMatchObject({ listed: false, fuel: "ev", price_segment: null });
});

test("a failed start shows a clear error and keeps the tiles usable", async () => {
  mockApi({ "/api/diagnosis/sessions": "offline" });
  render(<ProblemStep vehicle={SWIFT} />);
  fireEvent.click(await screen.findByRole("button", { name: /AC not cooling/ }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/couldn't reach our server/);
  expect(screen.getByRole("button", { name: /Tyres/ })).toHaveProperty("disabled", false);
});
