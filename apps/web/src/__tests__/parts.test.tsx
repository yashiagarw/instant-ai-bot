import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { PartCompareView } from "@/components/parts/part-compare";
import { PartDetailView } from "@/components/parts/part-detail";
import { ResultView } from "@/components/result/result-view";
import { rupeeRange, rupees } from "@/lib/format";
import { mockApi } from "./api-mock";
import { FakeDiagnosis } from "./fake-diagnosis";
import { PARTS_ROUTES } from "./parts-data";

let params: Record<string, string> = {};
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useParams: () => params,
  useSearchParams: () => search,
  useRouter: () => ({ push: vi.fn() }),
}));

let fake: FakeDiagnosis;
let fetchMock: ReturnType<typeof mockApi>;

function startSession(vehicle: Record<string, unknown> = { variant_id: 16 }) {
  const r = fake.handle("POST", "/api/diagnosis/sessions", { vehicle, topic_id: "tyres" })!;
  const id = (r.json as { session_id: string }).session_id;
  for (const a of [85, 91]) {
    const s = fake.sessions.get(id)!;
    fake.handle("POST", `/api/diagnosis/sessions/${id}/answers`, { question_id: s.flow[s.answers.length]?.id, option_id: a });
  }
  params = { sessionId: id };
  return id;
}

function calls(prefix: string): URL[] {
  return fetchMock.mock.calls.map(([u]) => new URL(String(u))).filter((u) => u.pathname.startsWith(prefix));
}

beforeEach(() => {
  fake = new FakeDiagnosis();
  fetchMock = mockApi(Object.fromEntries(PARTS_ROUTES), fake);
  search = new URLSearchParams();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("rupees use Indian digit grouping", () => {
  expect(rupees(1234567)).toBe("₹12,34,567");
  expect(rupees(600)).toBe("₹600");
  expect(rupeeRange(9800, 12750)).toBe("₹9,800 – ₹12,750");
  expect(rupeeRange(600, 600)).toBe("₹600");
});

test("parts you may need: fits your car, fit not verified, brand types and Indian prices", async () => {
  startSession();
  render(<ResultView />);
  const section = (await screen.findByRole("heading", { name: "Parts you may need" })).closest("section")!;
  const cards = await within(section).findAllByTestId("part-card");
  expect(cards).toHaveLength(3);

  const valve = within(section).getByRole("article", { name: "Tyre valve (tubeless)" });
  expect(within(valve).getByTestId("fit-badge").textContent).toBe("Fits your car");
  expect(within(valve).getByText("Genuine (OEM)")).toBeDefined();
  expect(within(valve).getByTestId("part-price").textContent).toBe("₹185");
  expect(within(valve).getByRole("img").getAttribute("alt")).toBe("Illustration: Tubeless tyre valve");
  expect(within(valve).getByRole("link", { name: "Tyre valve (tubeless)" }).getAttribute("href")).toBe("/parts/101?variant_id=16");

  // The unverified-fit case: a segment part with no compatibility record for this car.
  const kit = within(section).getByRole("article", { name: "Puncture repair kit (plug type)" });
  expect(within(kit).getByTestId("fit-badge").textContent).toBe("Fit not verified for your car");
  expect(within(kit).getByText("Any good brand")).toBeDefined();
  expect(within(kit).getByTestId("part-price").textContent).toBe("₹250 – ₹1,400");
  expect(within(kit).queryByRole("img")).toBeNull(); // no picture: a placeholder icon

  const sealant = within(section).getByRole("article", { name: "Tyre sealant" });
  expect(within(sealant).getByText("Aftermarket")).toBeDefined();
  expect(within(sealant).getByText("Only if needed")).toBeDefined();
  expect(within(sealant).getByTestId("part-price").textContent).toBe("₹12,34,567");

  expect(calls("/api/faults/")[0].search).toBe("?variant_id=16");
});

test("pick up to 3 parts to compare", async () => {
  startSession();
  render(<ResultView />);
  const section = (await screen.findByRole("heading", { name: "Parts you may need" })).closest("section")!;
  await within(section).findAllByTestId("part-card");
  const boxes = within(section).getAllByRole("checkbox", { name: "Compare" });
  fireEvent.click(boxes[0]);
  expect(within(section).queryByRole("link", { name: /Compare/ })).toBeNull(); // one part is not a comparison
  fireEvent.click(boxes[1]);
  expect(within(section).getByRole("link", { name: "Compare 2 parts" }).getAttribute("href")).toBe(
    "/parts/compare?ids=101,102&variant_id=16",
  );
  fireEvent.click(boxes[2]);
  expect(within(section).getByText("3 of 3 picked to compare.")).toBeDefined();
});

test("estimated cost: range, breakdown, metro label, sources and dates, one calm verification line", async () => {
  startSession();
  render(<ResultView />);
  const top = await screen.findByRole("article", { name: "Slow/pinhole puncture" });
  const card = await within(top).findByTestId("estimate");
  expect(within(card).getByTestId("estimate-total").textContent).toBe("₹600");
  expect(within(card).getByTestId("estimate-breakdown").textContent).toBe("Parts₹185Labour₹150Consumables₹250");
  expect(within(card).getByTestId("labour-basis").textContent).toBe("Delhi NCR metro estimate");
  expect(within(card).getByText("The final price depends on the mechanic's inspection.")).toBeDefined();
  const sources = within(card).getByTestId("estimate-sources").textContent!;
  expect(sources).toContain("Part: Tyre valve₹185");
  expect(sources).toContain("Checked 22 Oct 2026");
  expect(sources).toContain("Check date not recorded");
  expect(sources).toContain("Source: F12-B_VALVE");
  // needs_check is on every estimate: one calm line, not a warning on each card
  expect(screen.getAllByText("Prices are being verified with our mechanics.")).toHaveLength(1);
  expect(screen.getByTestId("area-note").textContent).toBe("Delhi NCR metro estimate");
});

test("your area: a zone or a pincode re-fetches the estimate", async () => {
  const id = startSession();
  render(<ResultView />);
  const top = await screen.findByRole("article", { name: "Slow/pinhole puncture" });
  await within(top).findByTestId("estimate");

  fireEvent.click(within(top).getByLabelText("Gurugram"));
  await waitFor(() => expect(within(top).getByTestId("estimate-total").textContent).toBe("₹750 – ₹1,150"));
  expect(within(top).getByTestId("labour-basis").textContent).toBe("Labour rate for Gurugram");
  expect(screen.getByTestId("area-note").textContent).toBe("Labour priced for Gurugram");
  expect(calls("/api/estimates").at(-1)!.search).toBe(`?session_id=${id}&zone=gurugram`);

  const pin = within(top).getByLabelText("Or your pincode");
  fireEvent.change(pin, { target: { value: "2013" } });
  fireEvent.click(within(top).getByRole("button", { name: "Use pincode" }));
  expect(within(top).getByText("Enter a 6-digit pincode")).toBeDefined();
  fireEvent.change(pin, { target: { value: "201309" } });
  fireEvent.click(within(top).getByRole("button", { name: "Use pincode" }));
  await waitFor(() => expect(screen.getByTestId("area-note").textContent).toBe("Labour priced for Noida"));
  expect(calls("/api/estimates").at(-1)!.search).toBe(`?session_id=${id}&pincode=201309`);

  fireEvent.change(pin, { target: { value: "400001" } });
  fireEvent.click(within(top).getByRole("button", { name: "Use pincode" }));
  await waitFor(() => expect(screen.getByTestId("area-note").textContent).toMatch(/not in our Delhi NCR zones/));
  expect(within(top).getByTestId("labour-basis").textContent).toBe("Delhi NCR metro estimate");
});

test("not enough data: Price on inspection with Request a Mechanic, never blank", async () => {
  const id = startSession();
  render(<ResultView />);
  const others = (await screen.findByRole("heading", { name: "Other possible causes" })).closest("section")!;
  const valve = others.querySelectorAll("details")[0] as HTMLElement;
  const card = await within(valve).findByTestId("estimate");
  expect(within(card).getByTestId("estimate-total").textContent).toBe("Price on inspection");
  expect(within(card).getByRole("link", { name: "Request a Mechanic" }).getAttribute("href")).toBe(`/request?session=${id}`);
});

test("part detail: fit for the car, prices with dates, models it is listed for, what it fixes", async () => {
  params = { id: "101" };
  search = new URLSearchParams("variant_id=16");
  render(<PartDetailView />);
  expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("Tyre valve (tubeless)");
  expect(screen.getByTestId("fit-badge").textContent).toBe("Fits your car");
  expect(screen.getByText("₹185")).toBeDefined();
  expect(screen.getByText("Checked 22 Oct 2026")).toBeDefined();
  expect(screen.getByText(/GST included · Fitting extra/)).toBeDefined();
  expect(screen.getByText("Maruti Suzuki Swift 2024–now")).toBeDefined();
  expect(screen.getByText("Slow/pinhole puncture")).toBeDefined();
  expect(screen.getByText("The final price depends on the mechanic's inspection.")).toBeDefined();
});

test("part detail without a car shows no fit; an unknown part shows an error", async () => {
  params = { id: "102" };
  render(<PartDetailView />);
  await screen.findByRole("heading", { level: 1 });
  expect(screen.queryByTestId("fit-badge")).toBeNull();
  expect(screen.getByText(/Pick your car in a diagnosis/)).toBeDefined();
  cleanup();
  params = { id: "999" };
  render(<PartDetailView />);
  expect(await screen.findByText(/couldn't find that/i)).toBeDefined();
});

test("compare: up to 3 parts side by side, including a part whose fit is not verified", async () => {
  search = new URLSearchParams("ids=101,102,103,104&variant_id=16");
  render(<PartCompareView />);
  const table = await screen.findByTestId("compare-table");
  const columns = within(table).getAllByRole("columnheader");
  expect(columns.map((c) => c.textContent)).toEqual([
    expect.stringContaining("Tyre valve (tubeless)"),
    expect.stringContaining("Puncture repair kit (plug type)"),
    expect.stringContaining("Tyre sealant"),
  ]);
  expect(calls("/api/parts/compare")[0].searchParams.get("ids")).toBe("101,102,103"); // the 4th id is dropped
  const fits = within(table).getAllByTestId("fit-badge").map((b) => b.textContent);
  expect(fits).toEqual(["Fits your car", "Fit not verified for your car", "Fit not verified for your car"]);
  expect(within(table).getByText("₹12,34,567")).toBeDefined();
  expect(within(table).getByRole("rowheader", { name: "Price checked" })).toBeDefined();
});

test("compare with no ids explains how to pick parts", () => {
  render(<PartCompareView />);
  expect(screen.getByText(/Pick up to 3 parts on your result page/)).toBeDefined();
});
