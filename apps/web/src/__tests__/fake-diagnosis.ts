// A small in-memory stand-in for the diagnosis API, shared by the Vitest mocks and the Playwright tests.
// It follows the real API's shapes; the flows are fixed:
//   tyres (tile)        → 2 questions; "It feels unsafe to drive" adds a high-risk alert for the top cause
//                          (red banner) and continues; the result also folds a medium alert into the tips
//   flat_tyre (emergency) → 1 fast-track question, then safety tips
//   text with "smoke"   → a high safety alert at once, done
import type {
  AnswerOut,
  CoverageLevel,
  Mode,
  Question,
  RankedFault,
  ResultOut,
  SafetyAlert,
  SessionOut,
  SessionState,
  VehicleSummary,
} from "../lib/api";
import { VARIANTS } from "./api-data";

export const Q_MAIN: Question = {
  id: 23,
  text: "What problem are you facing with your tyre?",
  category: "tyre",
  options: [
    { id: 84, label: "One tyre looks a little soft", not_sure: false },
    { id: 85, label: "The tyre goes soft again after I fill it with air", not_sure: false },
    { id: 86, label: "It feels unsafe to drive", not_sure: false },
    { id: 89, label: "Not sure", not_sure: true },
  ],
};
export const Q_FOLLOW: Question = {
  id: 24,
  text: "After filling the tyre with air, how soon does it go soft again?",
  category: "tyre",
  options: [
    { id: 90, label: "Within minutes", not_sure: false },
    { id: 91, label: "Within hours or days", not_sure: false },
    { id: 92, label: "Not sure", not_sure: true },
  ],
};
export const Q_FAST: Question = {
  id: 300,
  text: "Is the car parked in a safe place?",
  category: "tyre",
  options: [
    { id: 301, label: "Yes, away from traffic", not_sure: false },
    { id: 302, label: "No, it is on the road", not_sure: false },
    { id: 303, label: "Not sure", not_sure: true },
  ],
};

export const ALERT_ANSWER: SafetyAlert = {
  rule_id: 7,
  risk: "high",
  reason: "Likely cause: Slow/pinhole puncture",
  source: "likely",
  roadside_action: "Slow down and stop in a safe place away from traffic.",
  stop_driving_trigger: "",
  towing: "",
  fault_key: "F04-TY-02",
};
/** A medium-risk rule that fired: the API shows its advice as a tip, never in the red banner. */
export const MEDIUM_TIP = "Drive slowly to the nearest tyre shop.";
export const ALERT_SMOKE: SafetyAlert = {
  rule_id: 9,
  risk: "high",
  reason: "Words: smoke",
  source: "text",
  roadside_action: "Stop the car, switch off the engine and get everyone out.",
  stop_driving_trigger: "Stop if there is smoke, a burning smell or flames.",
  towing: "Tow the car. Do not drive it.",
  fault_key: null,
};

const MECHANIC_STEPS = [
  "Mechanic finds the leak using soapy water.",
  "Remove the wheel and look inside the tyre.",
  "Repair with a patch-plug.",
  "Balance the wheel.",
  "Set the correct pressure.",
  "Check again after 24 hours.",
  "Parts are replaced only when the test confirms.",
];

export const FAULTS: RankedFault[] = [
  {
    rank: 1,
    fault_key: "F04-TY-02",
    name: "Slow/pinhole puncture",
    category: "tyre",
    score: 3.7,
    confidence: "high",
    evidence: ["Main problem: The tyre goes soft again after I fill it with air", "Answer: Within hours or days"],
    diagnostic_steps: [],
    what_you_can_do: ["Park safely, check the pressure, do not pull out the nail."],
    what_the_mechanic_will_do: MECHANIC_STEPS,
    cost: null,
    repair_time: "Puncture repair: 20-30 minutes.",
    media: [
      { file: "F04/F04-TY-02.svg", caption: "Finding a slow leak with soapy water", image_code: "TY-02-1", role: "main", start_time: null, estimated_repair_time: "20-30 minutes" },
    ],
  },
  {
    rank: 2,
    fault_key: "F04-TY-04",
    name: "Valve issue",
    category: "tyre",
    score: 0.8,
    confidence: "low",
    evidence: ["Answer: Within hours or days"],
    diagnostic_steps: ["Put soapy water on the valve."],
    what_you_can_do: ["Keep the valve cap on."],
    what_the_mechanic_will_do: ["Change the valve core."],
    cost: null,
    repair_time: "10-15 minutes.",
    media: [],
  },
  {
    rank: 3,
    fault_key: "F04-TY-03",
    name: "Flat tyre",
    category: "tyre",
    score: 0,
    confidence: "low",
    evidence: [],
    diagnostic_steps: [],
    what_you_can_do: [],
    what_the_mechanic_will_do: ["Fit the spare wheel."],
    cost: null,
    repair_time: "",
    media: [],
  },
];

const TIPS = ["Park safely, away from traffic.", "Switch on the hazard lights."];
const DISCLAIMER =
  "This is an estimate based on your answers and our data. It is not a replacement for a professional inspection by a mechanic.";

interface FakeSession {
  id: string;
  vehicle: VehicleSummary;
  topic: string | null;
  mode: Mode;
  flow: Question[];
  answers: { question: Question; optionId: number | string }[];
  alerts: SafetyAlert[];
  stopped: boolean;
  feedback: { helpful: boolean; comment: string | null }[];
}

export interface FakeResponse {
  status: number;
  json: unknown;
}

const TOPICS: Record<string, { label: string; mode: Mode; flow: Question[] }> = {
  tyres: { label: "Tyres", mode: "diagnose", flow: [Q_MAIN, Q_FOLLOW] },
  flat_tyre: { label: "Flat tyre", mode: "fast_track", flow: [Q_FAST] },
};

export class FakeDiagnosis {
  sessions = new Map<string, FakeSession>();
  private next = 1;

  requests: Record<string, unknown>[] = [];

  handle(method: string, path: string, body?: unknown): FakeResponse | null {
    if (path === "/api/service-requests/config") return ok(REQUEST_CONFIG);
    if (path === "/api/service-requests" && method === "POST") return this.request(body as Record<string, unknown>);
    const m = path.match(/^\/api\/diagnosis\/sessions(?:\/([^/]+))?(\/.*)?$/);
    if (!m) return null;
    const [, id, rest = ""] = m;
    if (!id && method === "POST") return this.create(body as Record<string, unknown>);
    const s = id ? this.sessions.get(id) : undefined;
    if (!s) return { status: 404, json: { detail: "Session not found" } };
    if (method === "GET" && rest === "") return ok(this.state(s));
    if (method === "POST" && rest === "/answers") return this.answer(s, body as { question_id: number; option_id: number | string });
    if (method === "POST" && rest === "/answers/undo") return this.undo(s);
    if (method === "GET" && rest === "/result") return ok(this.result(s));
    if (method === "POST" && rest === "/feedback") {
      const b = body as { helpful: boolean; comment: string | null };
      s.feedback.push(b);
      return { status: 201, json: { id: s.feedback.length, session_id: s.id, helpful: b.helpful, created_at: NOW } };
    }
    return { status: 405, json: {} };
  }

  private create(body: Record<string, unknown>): FakeResponse {
    const id = `00000000-0000-4000-8000-${String(this.next++).padStart(12, "0")}`;
    const topicId = (body.topic_id as string | null) ?? "tyres";
    const topic = TOPICS[topicId] ?? TOPICS.tyres;
    const text = String(body.text ?? "");
    const s: FakeSession = {
      id,
      vehicle: vehicleOf(body.vehicle as Record<string, unknown>),
      topic: body.topic_id ? topic.label : null,
      mode: topic.mode,
      flow: topic.flow,
      answers: [],
      alerts: /smoke|dhuan/i.test(text) ? [ALERT_SMOKE] : [],
      stopped: /smoke|dhuan/i.test(text),
      feedback: [],
    };
    this.sessions.set(id, s);
    const out: SessionOut = {
      session_id: id,
      status: this.done(s) ? "completed" : "in_progress",
      mode: s.mode,
      coverage_level: coverage(s),
      safety_alerts: s.alerts,
      question: this.pending(s),
      done: this.done(s),
      safety_tips: [],
      actions: ["request_mechanic"],
      suggested_categories: [],
      progress: this.progress(s),
      disclaimer: DISCLAIMER,
    };
    return { status: 201, json: out };
  }

  private answer(s: FakeSession, body: { question_id: number; option_id: number | string }): FakeResponse {
    if (this.done(s)) return { status: 409, json: { detail: "this session is already completed" } };
    const q = this.pending(s)!;
    if (String(q.id) !== String(body.question_id)) return { status: 422, json: { detail: "not the current question" } };
    const option = q.options.find((o) => (body.option_id === "not_sure" ? o.not_sure : String(o.id) === String(body.option_id)));
    if (!option) return { status: 422, json: { detail: "unknown option" } };
    s.answers.push({ question: q, optionId: option.id });
    const fresh = option.id === 86 && !s.alerts.includes(ALERT_ANSWER) ? [ALERT_ANSWER] : [];
    s.alerts.push(...fresh);
    return ok({ ...this.turn(s), new_safety_alerts: fresh });
  }

  private undo(s: FakeSession): FakeResponse {
    if (this.done(s) || !s.answers.length) return { status: 409, json: { detail: "nothing to take back" } };
    const last = s.answers.pop()!;
    return ok({ ...this.turn(s), previous_option_id: last.optionId });
  }

  private request(b: Record<string, unknown>): FakeResponse {
    const phone = String(b.phone ?? "").replace(/[\s().-]/g, "");
    if (!/^(?:\+?91|0)?[6-9]\d{9}$/.test(phone)) return { status: 422, json: { detail: [{ msg: "mobile" }] } };
    if (b.consent !== true || b.consent_text_version !== REQUEST_CONFIG.consent_version) {
      return { status: 422, json: { detail: [{ msg: "consent is required" }] } };
    }
    const s = b.session_id ? this.sessions.get(String(b.session_id)) : undefined;
    const urgent = !!s && (s.mode === "fast_track" || s.alerts.some((a) => a.risk === "high"));
    if (!urgent && !b.pincode) return { status: 422, json: { detail: "enter a 6-digit pincode" } };
    this.requests.push({ ...b, urgent });
    const reference = `IM-TEST${this.requests.length}`;
    const helpline = REQUEST_CONFIG.helpline_number;
    return {
      status: 201,
      json: {
        reference,
        status: "submitted",
        urgent,
        created_at: NOW,
        helpline_number: helpline,
        next_steps: urgent
          ? [`We've marked your request urgent. Our team will call you as soon as possible. If you can't wait, call ${helpline}.`]
          : ["Our team will call you on your mobile to confirm the details and a time.", `Keep your reference ${reference} ready.`],
      },
    };
  }

  private pending(s: FakeSession): Question | null {
    return this.done(s) ? null : s.flow[s.answers.length];
  }

  private done(s: FakeSession): boolean {
    return s.stopped || s.answers.length >= s.flow.length;
  }

  private progress(s: FakeSession) {
    const number = s.answers.length + 1;
    return { question_number: number, questions_about: Math.max(s.mode === "fast_track" ? 3 : 8, number) };
  }

  private turn(s: FakeSession): AnswerOut {
    return {
      session_id: s.id,
      status: this.done(s) ? "completed" : "in_progress",
      question: this.pending(s),
      done: this.done(s),
      new_safety_alerts: [],
      safety_alerts: s.alerts,
      coverage_level: coverage(s),
      mode: s.mode,
      progress: this.progress(s),
    };
  }

  private state(s: FakeSession): SessionState {
    return { ...this.turn(s), vehicle: s.vehicle, topic: s.topic };
  }

  private result(s: FakeSession): ResultOut {
    const segment = s.vehicle.price_segment;
    const ranked = s.stopped
      ? []
      : FAULTS.map((f, i) => ({
          ...f,
          cost: segment
            ? {
                segment,
                display: i === 2 ? ("on_inspection" as const) : ("amount" as const),
                amount: i === 2 ? null : 230 + i * 10,
                min: null,
                max: null,
                text: null,
                approx_label: i === 0 ? "approx - ask shop" : null,
                checked_on: i === 0 ? "2026-10-12" : null,
                is_approx: true,
                labour: i === 0 ? 150 : null,
                labour_text: null,
              }
            : null,
        }));
    return {
      session_id: s.id,
      status: this.done(s) ? "completed" : "in_progress",
      mode: s.mode,
      vehicle: s.vehicle,
      topic: s.topic,
      engine_version: "1.0.0",
      coverage_level: coverage(s),
      stop_reason: this.done(s) ? (s.stopped ? "safety" : "leader_clear") : null,
      ranked,
      safety_alerts: s.alerts,
      roadside: {
        verdict: s.stopped ? "do_not_drive" : "roadside_limited",
        text: "Limited. A mechanic can find the leak by the road; the repair is at a tyre shop.",
        towing: "No.",
      },
      safety_tips: s.stopped ? TIPS : [MEDIUM_TIP, ...TIPS],
      actions: ["request_mechanic"],
      disclaimer: DISCLAIMER,
      created_at: NOW,
      completed_at: this.done(s) ? NOW : null,
      answers: s.answers.map((a) => ({
        question: a.question.text,
        answer: a.question.options.find((o) => o.id === a.optionId)!.label,
        asked_at: NOW,
        answered_at: NOW,
      })),
    };
  }
}

const NOW = "2026-10-24T10:00:00Z";

export const REQUEST_CONFIG = {
  consent_version: "request-v1",
  consent_text:
    "I agree that Instant Mechanic's team may use my name, mobile number, location and the car and diagnosis details above to contact me and arrange help for this request.",
  helpline_number: "+91-00000-11111",
  preferred_times: [
    { value: "asap", label: "As soon as possible" },
    { value: "today", label: "Later today" },
    { value: "tomorrow_morning", label: "Tomorrow morning" },
    { value: "tomorrow_evening", label: "Tomorrow evening" },
  ],
};

function ok(json: unknown): FakeResponse {
  return { status: 200, json };
}

function coverage(s: FakeSession): CoverageLevel {
  return s.vehicle.price_segment ? "segment_estimate" : "general_guidance";
}

function vehicleOf(v: Record<string, unknown>): VehicleSummary {
  if ("variant_id" in v) {
    const variant = VARIANTS.find((x) => x.id === v.variant_id) ?? VARIANTS[0];
    return {
      label: `Maruti Suzuki Swift · ${variant.name}`,
      listed: true,
      fuel: variant.fuel,
      transmission: variant.transmission,
      price_segment: variant.price_segment,
    };
  }
  const u = v.unlisted as Record<string, string | number | null>;
  return {
    label: [u.make, u.model, u.year].filter(Boolean).join(" "),
    listed: false,
    fuel: (u.fuel as VehicleSummary["fuel"]) ?? null,
    transmission: (u.transmission as VehicleSummary["transmission"]) ?? null,
    price_segment: (u.price_segment as VehicleSummary["price_segment"]) ?? null,
  };
}
