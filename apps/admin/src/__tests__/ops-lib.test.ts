import { expect, test } from "vitest";

import {
  age,
  channelLabel,
  needsNote,
  notificationOutcome,
  outcomeProblems,
  plainMoves,
  precisionNote,
  queueQuery,
  shiftProblem,
  templateLabel,
} from "@/lib/ops";
import { isMobile } from "@/lib/schemas";

test("plain status moves leave out offered / accepted / completed (they have their own actions)", () => {
  expect(plainMoves(["offered", "cancelled", "escalated"])).toEqual(["escalated", "cancelled"]);
  expect(plainMoves(["completed", "escalated"])).toEqual(["escalated"]);
  expect(plainMoves(["arrived", "triaged", "cancelled", "escalated"])).toEqual(["triaged", "arrived", "escalated", "cancelled"]);
  expect(needsNote("cancelled") && needsNote("escalated") && !needsNote("arrived")).toBe(true);
});

test("waiting time, rough points and the queue's filters from the address", () => {
  expect([age(4), age(60), age(125), age(1440), age(4000)]).toEqual(["4 min", "1 h", "2 h 5 min", "1 day", "2 days"]);
  expect([precisionNote("rough"), precisionNote("zone"), precisionNote("pincode"), precisionNote(null)]).toEqual([
    "rough location",
    "area centre only",
    "",
    "",
  ]);
  expect(queueQuery(new URLSearchParams("view=closed&safety=high&mine=1&q=IM-1"))).toEqual({
    view: "closed",
    status: undefined,
    safety: "high",
    category: undefined,
    mine: true,
    q: "IM-1",
  });
  expect(queueQuery(new URLSearchParams("view=bogus")).view).toBe("open");
});

test("shifts: end after start, no overlaps on a day", () => {
  const s = (weekday: number, start_time: string, end_time: string) => ({ weekday, start_time, end_time });
  expect(shiftProblem([s(0, "09:00", "13:00"), s(0, "13:00", "18:00"), s(1, "09:00", "18:00")])).toBeNull();
  expect(shiftProblem([s(0, "09:00", "13:00"), s(0, "12:00", "18:00")])).toBe("Monday: two shifts overlap.");
  expect(shiftProblem([s(6, "22:00", "02:00")])).toMatch(/^Sunday: a shift ends after it starts/);
  expect(shiftProblem([s(2, "", "10:00")])).toMatch(/^Wednesday: give a start/);
});

test("complete-job form: a fault, a description for other, named parts, a positive cost", () => {
  const ok = { confirmed_fault_key: "F08-BT-01", other_text: "", parts_used: [], final_cost_inr: null, mechanic_notes: "" };
  expect(outcomeProblems(ok)).toEqual({});
  expect(Object.keys(outcomeProblems({ ...ok, confirmed_fault_key: "" }))).toEqual(["confirmed_fault_key"]);
  expect(Object.keys(outcomeProblems({ ...ok, confirmed_fault_key: "other" }))).toEqual(["other_text"]);
  expect(outcomeProblems({ ...ok, parts_used: [{ name: " ", quantity: 1, price_inr: null }], final_cost_inr: -5 })).toEqual({
    "part-0": "Give the part's name, or remove the row.",
    final_cost_inr: "The final cost is a positive amount in rupees.",
  });
});

test("mechanic mobile numbers", () => {
  expect(["9000000007", "+91 90000 00007", "919000000007"].every(isMobile)).toBe(true);
  expect(["5000000007", "900000000", "+1 9000000007"].some(isMobile)).toBe(false);
});

test("notifications read as plain words, with the reason when one was not sent", () => {
  expect([templateLabel("job_offer"), templateLabel("mechanic_en_route"), templateLabel("new_thing")]).toEqual([
    "Job offer",
    "On the way",
    "new thing",
  ]);
  expect([channelLabel("whatsapp"), channelLabel("push"), channelLabel("sms")]).toEqual(["WhatsApp", "Browser alert", "SMS"]);
  expect(notificationOutcome({ status: "sent", error: null, attempts: 1 })).toBe("sent");
  expect(notificationOutcome({ status: "skipped", error: "WHATSAPP_TPL_JOB_OFFER is not set", attempts: 0 })).toBe(
    "skipped: WHATSAPP_TPL_JOB_OFFER is not set",
  );
  expect(notificationOutcome({ status: "queued", error: "MSG91 not reachable", attempts: 2 })).toBe(
    "retrying (attempt 2 failed: MSG91 not reachable)",
  );
  expect(notificationOutcome({ status: "queued", error: null, attempts: 0 })).toBe("queued");
});
