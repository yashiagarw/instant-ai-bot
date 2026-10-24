import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { ResultView } from "@/components/result/result-view";
import { mockApi } from "./api-mock";
import { FakeDiagnosis } from "./fake-diagnosis";

let sessionId = "";
vi.mock("next/navigation", () => ({ useParams: () => ({ sessionId }), useRouter: () => ({ push: vi.fn() }) }));

let fake: FakeDiagnosis;

function finished(body: Record<string, unknown>, answers: (number | string)[] = []) {
  const r = fake.handle("POST", "/api/diagnosis/sessions", body)!;
  sessionId = (r.json as { session_id: string }).session_id;
  const qs = [23, 24, 300];
  for (const a of answers) {
    const s = fake.sessions.get(sessionId)!;
    fake.handle("POST", `/api/diagnosis/sessions/${sessionId}/answers`, {
      question_id: s.flow[s.answers.length]?.id ?? qs[0],
      option_id: a,
    });
  }
}

beforeEach(() => {
  fake = new FakeDiagnosis();
  mockApi({}, fake);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("listed car: top cause with evidence, roadside verdict, segment cost with labour, approx and date", async () => {
  finished({ vehicle: { variant_id: 16 }, topic_id: "tyres" }, [85, 91]);
  render(<ResultView />);
  const top = await screen.findByRole("article", { name: "Slow/pinhole puncture" });
  expect(screen.getByTestId("coverage").textContent).toContain("Segment estimate");
  expect(within(top).getByText("Why we think this")).toBeDefined();
  expect(within(top).getAllByRole("listitem").map((li) => li.textContent)).toContain("Answer: Within hours or days");

  const roadside = within(top).getByTestId("roadside");
  expect(roadside.textContent).toContain("Roadside check, then a garage");
  expect(roadside.textContent).not.toMatch(/^Limited|Limited\./); // answer word stripped
  expect(roadside.textContent).toContain("When to tow: Usually not needed.");

  const cost = within(top).getByRole("region", { name: "Estimated cost" });
  expect(cost.textContent).toContain("₹230");
  expect(cost.textContent).toContain("Labour₹150");
  expect(cost.textContent).toContain("approx - ask shop");
  expect(cost.textContent).toContain("Price checked 12 Oct 2026");
  expect(cost.textContent).toContain("Puncture repair: 20-30 minutes.");
  expect(cost.textContent).toContain("For cars below ₹10 lakh");
});

test("sections without content are hidden; DIY and mechanic advice are separate; pictures are illustrations", async () => {
  finished({ vehicle: { variant_id: 16 }, topic_id: "tyres" }, [85, 91]);
  render(<ResultView />);
  const top = await screen.findByRole("article", { name: "Slow/pinhole puncture" });
  expect(within(top).queryByText("How it's checked")).toBeNull(); // no diagnostic steps for this fault
  expect(within(top).getByText("What you can do")).toBeDefined();
  expect(within(top).getByText("What the mechanic will do")).toBeDefined();
  expect(within(top).getByText(/repair needs a garage/)).toBeDefined();
  expect(within(top).getByText("Illustration")).toBeDefined();
  expect(within(top).getByRole("img").getAttribute("alt")).toBe("Illustration: Finding a slow leak with soapy water");
  expect(within(top).getByRole("img").getAttribute("src")).toBe("http://localhost:8000/media/F04/F04-TY-02.svg");

  const others = screen.getByRole("heading", { name: "Other possible causes" }).closest("section")!;
  const details = others.querySelectorAll("details");
  expect(details).toHaveLength(2);
  expect([...details].every((d) => !d.open)).toBe(true);
  expect(details[0].textContent).toContain("How it's checked"); // Valve issue has steps
  expect(details[1].textContent).not.toContain("What you can do"); // Flat tyre has none
  expect(details[1].textContent).toContain("Price after inspection");
});

test("disclaimer, feedback and a Request a Mechanic button that sticks on mobile", async () => {
  finished({ vehicle: { variant_id: 16 }, topic_id: "tyres" }, [85, 91]);
  render(<ResultView />);
  await screen.findByRole("article");
  expect(screen.getByTestId("disclaimer").textContent).toMatch(/not a replacement for a professional inspection/);
  const requests = screen.getAllByRole("link", { name: "Request a Mechanic" });
  expect(requests.map((a) => a.getAttribute("href"))).toEqual([`/request?session=${sessionId}`, `/request?session=${sessionId}`]);
  expect(requests[1].closest("div.fixed")?.className).toContain("md:hidden");

  fireEvent.click(screen.getByRole("button", { name: "No" }));
  fireEvent.change(screen.getByLabelText(/Anything to add/), { target: { value: "It was the valve" } });
  fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
  expect((await screen.findByRole("status")).textContent).toBe("Thanks for your feedback.");
  expect(fake.sessions.get(sessionId)!.feedback).toEqual([{ helpful: false, comment: "It was the valve" }]);
});

test("unlisted car without a price range: General guidance and no cost", async () => {
  finished({ vehicle: { unlisted: { make: "Hindustan", model: "Ambassador", year: 2010 } }, topic_id: "tyres" }, [85, 91]);
  render(<ResultView />);
  const top = await screen.findByRole("article");
  expect(screen.getByTestId("coverage").textContent).toContain("General guidance");
  expect(screen.getByTestId("car-summary").textContent).toContain("Hindustan Ambassador 2010");
  expect(within(top).getByText(/can't estimate the cost without your car's price range/)).toBeDefined();
  expect(within(top).queryByTestId("cost-total")).toBeNull();
});

test("a safety stop puts the red banner first", async () => {
  finished({ vehicle: { variant_id: 16 }, text: "smoke from the bonnet" });
  const { container } = render(<ResultView />);
  const banner = await screen.findByTestId("safety-banner");
  expect(container.querySelector("[data-testid]")).toBe(banner);
  expect(banner.textContent).toContain("Stop the car, switch off the engine");
  expect(banner.textContent).toContain("Towing: Tow the car. Do not drive it.");
  expect(screen.getByText(/couldn't narrow this down/)).toBeDefined();
});

test("fast-track result leads with safety tips and a large Request a Mechanic button", async () => {
  finished({ vehicle: { variant_id: 16 }, topic_id: "flat_tyre" }, [302]);
  render(<ResultView />);
  const tips = await screen.findByRole("region", { name: "Stay safe while help comes" });
  expect(within(tips).getByText("Switch on the hazard lights.")).toBeDefined();
  expect(within(tips).getByRole("link", { name: "Request a Mechanic" }).dataset.size).toBe("cta");
});

test("an unfinished session from a shared link shows the ranking so far and a way back", async () => {
  finished({ vehicle: { variant_id: 16 }, topic_id: "tyres" }, [85]);
  render(<ResultView />);
  const link = await screen.findByRole("link", { name: "Continue the questions" });
  expect(link.getAttribute("href")).toBe(`/diagnose/${sessionId}`);
});

test("an unknown session shows a clear error", async () => {
  sessionId = "00000000-0000-4000-8000-999999999999";
  render(<ResultView />);
  await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/couldn't find that/));
  expect(screen.getByRole("link", { name: "Start a new diagnosis" })).toBeDefined();
});

test("the mechanic's steps show 5 at first, the rest behind Show all", async () => {
  finished({ vehicle: { variant_id: 16 }, topic_id: "tyres" }, [85, 91]);
  render(<ResultView />);
  const top = await screen.findByRole("article", { name: "Slow/pinhole puncture" });
  const steps = within(top).getByText("What the mechanic will do").parentElement!;
  expect(within(steps).getAllByRole("listitem")).toHaveLength(5);
  const more = within(steps).getByRole("button", { name: "Show all 7 steps" });
  expect(more.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(more);
  expect(within(steps).getAllByRole("listitem")).toHaveLength(7);
  expect(within(steps).getByText("Parts are replaced only when the test confirms.")).toBeDefined();
  expect(within(steps).getByRole("button", { name: "Show fewer steps" }).getAttribute("aria-expanded")).toBe("true");
});

test("no red banner without a high-risk alert; lower-risk advice is in the safety tips", async () => {
  finished({ vehicle: { variant_id: 16 }, topic_id: "tyres" }, [85, 91]);
  render(<ResultView />);
  await screen.findByRole("article");
  expect(screen.queryByTestId("safety-banner")).toBeNull();
  const tips = screen.getByRole("region", { name: "Safety tips" });
  expect(within(tips).getByText("Drive slowly to the nearest tyre shop.")).toBeDefined();
});
