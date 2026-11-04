// Helpers for the Requests and Mechanics pages (backend/app/requests/workflow.py, backend/app/mechanics).

import type { OutcomeInput, Precision, QueueQuery, RequestStatus, SafetyLevel, Shift } from "@/lib/api";

export const STATUS_LABELS: Record<RequestStatus, string> = {
  submitted: "New",
  triaged: "Triaged",
  offered: "Offered to a mechanic",
  accepted: "Mechanic accepted",
  en_route: "Mechanic on the way",
  arrived: "Mechanic arrived",
  in_progress: "Repair in progress",
  completed: "Completed",
  cancelled: "Cancelled",
  escalated: "Escalated",
};

export const statusLabel = (s: string | null) => (s ? (STATUS_LABELS[s as RequestStatus] ?? s) : "");

/** The buttons for a plain status change: the label says what the agent did. */
export const MOVE_LABELS: Partial<Record<RequestStatus, string>> = {
  triaged: "Mark triaged",
  en_route: "Mechanic is on the way",
  arrived: "Mechanic arrived",
  in_progress: "Repair started",
  escalated: "Escalate",
  cancelled: "Cancel request",
};

/** offered, accepted and completed have their own actions (offer, the mechanic's answer, the complete-job form). */
const VIA_ACTION: RequestStatus[] = ["offered", "accepted", "completed"];

/** The plain moves allowed now, in the order of the usual path (escalate and cancel last). */
export function plainMoves(allowed: RequestStatus[]): RequestStatus[] {
  const order: RequestStatus[] = ["triaged", "en_route", "arrived", "in_progress", "escalated", "cancelled"];
  return order.filter((s) => allowed.includes(s) && !VIA_ACTION.includes(s));
}

/** Cancel and escalate need a short note saying why. */
export const needsNote = (s: RequestStatus) => s === "cancelled" || s === "escalated";

export const SAFETY_LABELS: Record<SafetyLevel, string> = {
  high: "Safety-critical",
  medium: "Safety: medium",
  low: "Safety: low",
  none: "No safety alert",
};

export const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }));

/** "4 min", "2 h 5 min", "3 days". */
export function age(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 24 * 60) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m ? `${h} h ${m} min` : `${h} h`;
  }
  const d = Math.floor(minutes / (24 * 60));
  return d === 1 ? "1 day" : `${d} days`;
}

/** What a map point's precision means, or "" when it is the pincode's own centre. */
export function precisionNote(p: Precision | null | undefined): string {
  if (p === "rough") return "rough location";
  if (p === "zone") return "area centre only";
  return "";
}

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** What is wrong with a week of shifts (the API refuses the same), or null. */
export function shiftProblem(shifts: Shift[]): string | null {
  const byDay = new Map<number, Shift[]>();
  for (const s of shifts) {
    if (!s.start_time || !s.end_time) return `${WEEKDAYS[s.weekday]}: give a start and an end time.`;
    if (s.end_time <= s.start_time) {
      return `${WEEKDAYS[s.weekday]}: a shift ends after it starts (split overnight shifts at midnight).`;
    }
    byDay.set(s.weekday, [...(byDay.get(s.weekday) ?? []), s]);
  }
  for (const [day, list] of byDay) {
    const sorted = [...list].sort((a, b) => a.start_time.localeCompare(b.start_time));
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i].start_time < sorted[i - 1].end_time) return `${WEEKDAYS[day]}: two shifts overlap.`;
    }
  }
  return null;
}

/** Field errors of the complete-job form (empty when it can be sent). */
export function outcomeProblems(o: OutcomeInput): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!o.confirmed_fault_key) errors.confirmed_fault_key = "Choose the fault the mechanic found, or Other.";
  if (o.confirmed_fault_key === "other" && !o.other_text.trim()) errors.other_text = "Say what the fault was.";
  o.parts_used.forEach((p, i) => {
    if (!p.name.trim()) errors[`part-${i}`] = "Give the part's name, or remove the row.";
    else if (!Number.isInteger(p.quantity) || p.quantity < 1) errors[`part-${i}`] = "The quantity is a whole number, 1 or more.";
  });
  if (o.final_cost_inr !== null && (!Number.isFinite(o.final_cost_inr) || o.final_cost_inr < 0)) {
    errors.final_cost_inr = "The final cost is a positive amount in rupees.";
  }
  return errors;
}

/** The queue's filters from the page address (so a filtered queue can be shared and survives a reload). */
export function queueQuery(params: URLSearchParams): QueueQuery {
  const view = params.get("view");
  return {
    view: view === "closed" || view === "all" ? view : "open",
    status: params.get("status") ?? undefined,
    safety: params.get("safety") ?? undefined,
    category: params.get("category") ?? undefined,
    mine: params.get("mine") === "1",
    q: params.get("q") ?? undefined,
  };
}

export const rupees = (n: number | null) => (n === null ? "" : `₹${n.toLocaleString("en-IN")}`);

// ---------------------------------------------------------------- notifications (request page, read-only)

const TEMPLATE_LABELS: Record<string, string> = {
  request_submitted: "New request alert",
  request_escalated: "Escalation alert",
  job_offer: "Job offer",
  mechanic_assigned: "Mechanic assigned",
  mechanic_en_route: "On the way",
  mechanic_arrived: "Arrived",
  job_completed: "Job done",
  offer_accepted_ack: "Reply: job confirmed",
  offer_declined_ack: "Reply: decline noted",
  offer_closed: "Reply: offer closed",
  whatsapp_stopped: "Reply: WhatsApp stopped",
  whatsapp_started: "Reply: WhatsApp started",
};
const CHANNEL_LABELS: Record<string, string> = { whatsapp: "WhatsApp", sms: "SMS", push: "Browser alert", email: "Email" };

export function templateLabel(template: string): string {
  return TEMPLATE_LABELS[template] ?? template.replaceAll("_", " ");
}

export function channelLabel(channel: string): string {
  return CHANNEL_LABELS[channel] ?? channel;
}

/** "sent", or "failed: <why>" / "skipped: <why>", or "queued (attempt 2 failed: <why>)". */
export function notificationOutcome(n: { status: string; error: string | null; attempts: number }): string {
  if (n.status === "queued") return n.error ? `retrying (attempt ${n.attempts} failed: ${n.error})` : "queued";
  if ((n.status === "failed" || n.status === "skipped") && n.error) return `${n.status}: ${n.error}`;
  return n.status;
}
