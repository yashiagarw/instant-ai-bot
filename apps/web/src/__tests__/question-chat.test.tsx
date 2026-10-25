import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { QuestionChat } from "@/components/diagnose/question-chat";
import { mockApi } from "./api-mock";
import { FakeDiagnosis } from "./fake-diagnosis";

const replace = vi.fn();
let sessionId = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  useParams: () => ({ sessionId }),
}));

let fake: FakeDiagnosis;

function startSession(body: Record<string, unknown>) {
  const r = fake.handle("POST", "/api/diagnosis/sessions", body)!;
  sessionId = (r.json as { session_id: string }).session_id;
}

beforeEach(() => {
  replace.mockReset();
  fake = new FakeDiagnosis();
  mockApi({}, fake);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("shows the car, one question with Not sure, and the progress", async () => {
  startSession({ vehicle: { variant_id: 16 }, topic_id: "tyres" });
  render(<QuestionChat />);
  expect(await screen.findByRole("heading", { name: /What problem are you facing/ })).toBeDefined();
  expect(screen.getByTestId("car-summary").textContent).toContain("Maruti Suzuki Swift");
  expect(screen.getByTestId("car-summary").textContent).toContain("Tyres");
  expect(screen.getByText("Question 1 of about 8")).toBeDefined();
  expect(screen.getByRole("button", { name: "Not sure" })).toBeDefined();
  expect(screen.getByRole("link", { name: /Change problem/ }).getAttribute("href")).toBe("/diagnose?step=problem");
});

test("a safety answer shows the red banner at once; back reopens the question; the end opens the result", async () => {
  startSession({ vehicle: { variant_id: 16 }, topic_id: "tyres" });
  render(<QuestionChat />);
  fireEvent.click(await screen.findByRole("button", { name: "It feels unsafe to drive" }));
  const banner = await screen.findByTestId("safety-banner");
  expect(banner.getAttribute("role")).toBe("alert");
  expect(banner.textContent).toContain("Slow down and stop in a safe place");
  expect(banner.textContent).not.toMatch(/Not stated|Depends/);
  expect(screen.getByText("Question 2 of about 8")).toBeDefined();
  await waitFor(() => expect(document.activeElement?.id).toBe("question-heading"));

  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  const previous = await screen.findByRole("button", { name: "It feels unsafe to drive" });
  expect(previous.getAttribute("aria-describedby")).toBe("previous-answer");
  fireEvent.click(screen.getByRole("button", { name: "The tyre goes soft again after I fill it with air" }));
  await screen.findByText("Question 2 of about 8");
  fireEvent.click(screen.getByRole("button", { name: "Not sure" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith(`/diagnose/${sessionId}/result`));
});

test("a session stopped for safety goes straight to the result", async () => {
  startSession({ vehicle: { variant_id: 16 }, text: "engine se smoke aa raha hai" });
  render(<QuestionChat />);
  await waitFor(() => expect(replace).toHaveBeenCalledWith(`/diagnose/${sessionId}/result`));
});

test("fast-track topics count to about 3", async () => {
  startSession({ vehicle: { variant_id: 16 }, topic_id: "flat_tyre" });
  render(<QuestionChat />);
  expect(await screen.findByText("Question 1 of about 3")).toBeDefined();
});

test("an unknown session shows a clear message", async () => {
  sessionId = "00000000-0000-4000-8000-999999999999";
  render(<QuestionChat />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/couldn't find that/);
});

test("a typed reply shows what we understood and the same question comes back", async () => {
  startSession({ vehicle: { variant_id: 16 }, topic_id: "tyres" });
  render(<QuestionChat />);
  await screen.findByRole("heading", { name: /What problem are you facing/ });
  const box = screen.getByLabelText("Or type your answer in your own words");
  fireEvent.change(box, { target: { value: "hawa 2 din mein kam ho jaati hai" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  const chip = await screen.findByRole("button", { name: /We understood: tyre goes soft again/ });
  expect(chip.getAttribute("aria-expanded")).toBe("false");
  expect(screen.getByText("hawa 2 din mein kam ho jaati hai")).toBeDefined();
  expect((box as HTMLTextAreaElement).value).toBe("");
  expect(screen.getByText("Question 1 of about 8")).toBeDefined(); // typed words never answer it on their own
  expect(fake.sessions.get(sessionId)!.messages).toEqual(["hawa 2 din mein kam ho jaati hai"]);
});

test("tapping the chip lets you take the message back and edit it", async () => {
  startSession({ vehicle: { variant_id: 16 }, topic_id: "tyres" });
  render(<QuestionChat />);
  await screen.findByRole("heading", { name: /What problem are you facing/ });
  const box = screen.getByLabelText("Or type your answer in your own words") as HTMLTextAreaElement;
  fireEvent.change(box, { target: { value: "kuch ajeeb awaaz" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  fireEvent.click(await screen.findByRole("button", { name: /We added this to your description/ }));
  fireEvent.click(screen.getByRole("button", { name: "Edit my message" }));
  await waitFor(() => expect(box.value).toBe("kuch ajeeb awaaz"));
  expect(document.activeElement).toBe(box);
  expect(screen.queryByText(/We added this to your description/)).toBeNull();
  expect(fake.sessions.get(sessionId)!.messages).toEqual([]);
});

test("after tapping an answer, the earlier message can no longer be corrected", async () => {
  startSession({ vehicle: { variant_id: 16 }, topic_id: "tyres" });
  render(<QuestionChat />);
  await screen.findByRole("heading", { name: /What problem are you facing/ });
  fireEvent.change(screen.getByLabelText("Or type your answer in your own words"), { target: { value: "nail laga hai" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByRole("button", { name: /We understood: nail in the tyre/ });
  fireEvent.click(screen.getByRole("button", { name: "One tyre looks a little soft" }));
  await screen.findByText("Question 2 of about 8");
  expect(screen.queryByRole("button", { name: /We understood/ })).toBeNull();
  expect(screen.getByText(/We understood: nail in the tyre/)).toBeDefined(); // still shown, as plain text
});

test("an empty reply asks for words; smoke in a reply goes to the result", async () => {
  startSession({ vehicle: { variant_id: 16 }, topic_id: "tyres" });
  render(<QuestionChat />);
  await screen.findByRole("heading", { name: /What problem are you facing/ });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(screen.getByText(/Type a few words first/)).toBeDefined();
  fireEvent.change(screen.getByLabelText("Or type your answer in your own words"), { target: { value: "bonnet se smoke" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith(`/diagnose/${sessionId}/result`));
});
