import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { VehicleStep } from "@/components/diagnose/vehicle-step";
import { mockApi } from "./api-mock";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const searches = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls.map((c) => new URL(String(c[0]))).filter((u) => u.pathname === "/api/vehicles/search");

test("search is debounced and a result picks the car", async () => {
  const fetchMock = mockApi();
  const onDone = vi.fn();
  render(<VehicleStep onDone={onDone} />);
  const box = screen.getByLabelText("Search for your car");
  for (const text of ["s", "sw", "swi", "swift"]) fireEvent.change(box, { target: { value: text } });
  const hit = await screen.findByRole("button", { name: /Maruti Suzuki Swift/ });
  expect(searches(fetchMock).map((u) => u.searchParams.get("q"))).toEqual(["swift"]);
  fireEvent.click(hit);
  expect(onDone).toHaveBeenCalledWith({
    kind: "listed",
    variant_id: 16,
    price_segment: "budget",
    label: "Maruti Suzuki Swift · Petrol 1.2 AMT",
  });
});

test("no search results explains what to do", async () => {
  mockApi({ "/api/vehicles/search": { query: "zzz", year_matched: true, results: [] } });
  render(<VehicleStep onDone={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Search for your car"), { target: { value: "zzz" } });
  expect((await screen.findByText(/No cars match/)).textContent).toMatch(/My car isn.t listed/);
});

test("make, model, year, fuel and gearbox lead to the variant and its price range", async () => {
  mockApi();
  const onDone = vi.fn();
  render(<VehicleStep onDone={onDone} />);
  expect(screen.getByText(/loading makes/i).getAttribute("role")).toBe("status");
  fireEvent.click(await screen.findByRole("button", { name: "Maruti Suzuki" }));
  fireEvent.click(await screen.findByRole("button", { name: "Swift" }));
  fireEvent.click(await screen.findByRole("radio", { name: "2020" }));
  // Only petrol and manual exist for 2020, so they are answered already; two versions remain.
  expect(screen.getByRole("radio", { name: "Petrol" })).toHaveProperty("checked", true);
  expect(screen.getByRole("radio", { name: "Manual" })).toHaveProperty("checked", true);
  expect(screen.queryByRole("button", { name: /this is my car/i })).toBeNull();
  const versions = within(screen.getByRole("group", { name: "Which version?" }));
  fireEvent.click(versions.getByRole("radio", { name: /Petrol MT ZXi/ }));
  expect(screen.getByText(/₹10-25 lakh/)).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: /this is my car/i }));
  expect(onDone).toHaveBeenCalledWith({
    kind: "listed",
    variant_id: 11,
    price_segment: "mid",
    label: "Maruti Suzuki Swift 2020 · Petrol MT ZXi",
  });
});

test("changing the make clears the later picks", async () => {
  mockApi();
  render(<VehicleStep onDone={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Maruti Suzuki" }));
  fireEvent.click(await screen.findByRole("button", { name: "Swift" }));
  await screen.findByRole("radio", { name: "2024" });
  fireEvent.click(screen.getByRole("button", { name: "Change make" }));
  expect(screen.queryByRole("radio", { name: "2024" })).toBeNull();
  expect(screen.getByLabelText("Search for your car")).toBeDefined();
});

test("toggles are real radio buttons, so they work with the keyboard", async () => {
  mockApi();
  render(<VehicleStep onDone={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Maruti Suzuki" }));
  fireEvent.click(await screen.findByRole("button", { name: "Swift" }));
  const years = within(await screen.findByRole("group", { name: "Year" })).getAllByRole("radio");
  expect(new Set(years.map((r) => r.getAttribute("name"))).size).toBe(1);
});

test("a failed load shows a clear message and retries", async () => {
  mockApi({ "/api/vehicles/makes": "fail" });
  render(<VehicleStep onDone={vi.fn()} />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/went wrong on our side/i);
  mockApi();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("button", { name: "Hyundai" })).toBeDefined();
});

test("My car isn't listed: validates, then sends the typed car with Not sure as null", async () => {
  mockApi();
  const onDone = vi.fn();
  render(<VehicleStep onDone={onDone} />);
  fireEvent.click(screen.getByRole("button", { name: /my car isn.t listed/i }));
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(screen.getByText(/Type the make/)).toBeDefined();
  expect(screen.getByText(/Pick a price range/)).toBeDefined();
  await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText("Make")));
  expect(onDone).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText("Make"), { target: { value: " Hindustan " } });
  fireEvent.change(screen.getByLabelText("Model"), { target: { value: "Ambassador" } });
  fireEvent.change(screen.getByLabelText("Year"), { target: { value: "1975" } });
  fireEvent.click(within(screen.getByRole("group", { name: "Fuel" })).getByRole("radio", { name: "Diesel" }));
  fireEvent.click(within(screen.getByRole("group", { name: "Gearbox" })).getByRole("radio", { name: "Not sure" }));
  const price = within(screen.getByRole("group", { name: "Roughly what did the car cost new?" }));
  expect(price.getAllByRole("radio").map((r) => r.closest("div")!.textContent)).toEqual([
    "Below ₹10 lakh",
    "₹10-25 lakh",
    "Above ₹25 lakh",
    "Not sure",
  ]);
  fireEvent.click(price.getByRole("radio", { name: "Below ₹10 lakh" }));
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(screen.getByText(/between 1980 and/)).toBeDefined();

  fireEvent.change(screen.getByLabelText("Year"), { target: { value: "2010" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(onDone).toHaveBeenCalledWith({
    kind: "unlisted",
    label: "Hindustan Ambassador 2010",
    unlisted: { make: "Hindustan", model: "Ambassador", year: 2010, fuel: "diesel", transmission: null, price_segment: "budget" },
  });
});
