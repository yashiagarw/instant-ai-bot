// The /api/admin/requests and /api/admin/mechanics part of the fake API (see fake-admin.ts). Mirrors the rules the
// pages rely on (backend/app/requests/workflow.py, admin_api.py, backend/app/mechanics/admin_api.py): the queue order
// (safety-critical, urgent, oldest), masked phones that only the owning agent can reveal, the allowed status moves
// (cancel / escalate need a note), offers (a mechanic who is not a suggestion needs a note), the mechanic's answer,
// and completion with the confirmed fault (only in progress; "other" needs a description).

type Json = Record<string, unknown>;
type Result = { status: number; json?: unknown };

const MINUTE = 60_000;
const NOW = Date.now();
const ago = (min: number) => new Date(NOW - min * MINUTE).toISOString();

const TRANSITIONS: Record<string, string[]> = {
  submitted: ["triaged", "cancelled", "escalated"],
  triaged: ["offered", "cancelled", "escalated"],
  offered: ["accepted", "triaged", "cancelled", "escalated"],
  accepted: ["en_route", "triaged", "cancelled", "escalated"],
  en_route: ["arrived", "triaged", "cancelled", "escalated"],
  arrived: ["in_progress", "cancelled", "escalated"],
  in_progress: ["completed", "escalated"],
  escalated: ["triaged", "cancelled"],
  completed: [],
  cancelled: [],
};
const VIA_ACTION = ["offered", "accepted", "completed"];
const SAFETY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

export const CATEGORIES = [
  { code: "battery", name: "Battery", kind: "diagnose", beta: false, has_questions: true },
  { code: "brakes", name: "Brakes", kind: "diagnose", beta: false, has_questions: true },
  { code: "ac", name: "AC and cooling", kind: "diagnose", beta: false, has_questions: true },
];

const FAULTS = [
  { fault_key: "F08-BT-01", name: "Weak battery", category_code: "battery" },
  { fault_key: "F08-BT-02", name: "Loose battery terminal", category_code: "battery" },
  { fault_key: "F07-SS-01", name: "Starter motor fault", category_code: "battery" },
];

interface Req {
  id: string;
  reference: string;
  created_at: string;
  age_minutes: number;
  status: string;
  safety_level: string;
  urgent: boolean;
  name: string;
  phone: string;
  area: string;
  pincode: string;
  service_type: string;
  category_code: string | null;
  category: string | null;
  vehicle: string;
  problem_summary: string;
  owner: string | null; // the owning agent's email
  session_id: string | null;
  address: string;
  preferred_time: string;
  notes_from_customer: string;
  point: { lat: number; lon: number; precision: string } | null;
  causes: { rank: number; fault_key: string; name: string; confidence: string }[];
  assignments: Json[];
  events: Json[];
  internal_notes: Json[];
  outcome: Json | null;
  notifications: Json[];
}

let seq = 0;
function req(over: Partial<Req> & Pick<Req, "reference" | "age_minutes">): Req {
  const n = ++seq;
  return {
    id: `11111111-0000-4000-8000-${String(n).padStart(12, "0")}`,
    created_at: ago(over.age_minutes),
    status: "submitted",
    safety_level: "none",
    urgent: false,
    name: "Customer",
    phone: `+9198000000${String(n).padStart(2, "0")}`,
    area: "Malviya Nagar",
    pincode: "110017",
    service_type: "at_location",
    category_code: "battery",
    category: "Battery",
    vehicle: "Maruti Suzuki Swift 2018-2023 Petrol MT",
    problem_summary: "Car does not start, clicking sound",
    owner: null,
    session_id: "s-1",
    address: "B-12, Malviya Nagar",
    preferred_time: "As soon as possible",
    notes_from_customer: "",
    point: { lat: 28.5355, lon: 77.2066, precision: "pincode" },
    causes: [
      { rank: 1, fault_key: "F08-BT-01", name: "Weak battery", confidence: "high" },
      { rank: 2, fault_key: "F07-SS-01", name: "Starter motor fault", confidence: "medium" },
    ],
    assignments: [],
    events: [{ id: n * 100, at: ago(over.age_minutes), kind: "status", from_status: null, to_status: "submitted", actor: "customer", note: "", data: {} }],
    internal_notes: [],
    outcome: null,
    // Phase 5.2: the support alert went out; WhatsApp was not configured for the offer, so it fell back to SMS.
    notifications: [
      { id: n * 10, created_at: ago(over.age_minutes), event: "submitted", template: "request_submitted", language: "en",
        recipient: "support", to: "s***@example.com", channel: "email", status: "sent", attempts: 1, provider: "console",
        error: null, sent_at: ago(over.age_minutes), previous_id: null },
      { id: n * 10 + 1, created_at: ago(1), event: "offered", template: "job_offer", language: "hi", recipient: "mechanic",
        to: "+91******0001", channel: "whatsapp", status: "skipped", attempts: 0, provider: "whatsapp_cloud",
        error: "WHATSAPP_TPL_JOB_OFFER is not set (approved template name)", sent_at: null, previous_id: null },
      { id: n * 10 + 2, created_at: ago(1), event: "offered", template: "job_offer", language: "hi", recipient: "mechanic",
        to: "+91******0001", channel: "sms", status: "sent", attempts: 1, provider: "msg91", error: null, sent_at: ago(1),
        previous_id: n * 10 + 1 },
    ],
    ...over,
  };
}

function mechanic(id: number, name: string, over: Json = {}): Json {
  return {
    id, name, phone: `+91900000000${id}`, base_pincode: "110017", base_area: "Malviya Nagar", base_point: [28.5355, 77.2066],
    base_precision: "pincode", rating: 4.5, max_jobs_per_day: 4, on_duty: true, on_duty_changed_at: null, active: true,
    staff_user_id: null, notes: "", dev_seed: false, skills: ["battery"], zones: [{ pincode: "110017", radius_km: null,
    center_lat: null, center_lon: null, point: [28.5355, 77.2066], precision: "pincode" }], shifts: [], jobs_today: 1,
    acceptance_rate: 0.8, documents: null, ...over,
  }; // prettier-ignore
}

const mask = (phone: string) => `******${phone.slice(-4)}`;

export class FakeOps {
  requests: Req[] = [
    req({ reference: "IM-OLD001", age_minutes: 300, name: "Ravi Old" }),
    req({ reference: "IM-URG002", age_minutes: 60, urgent: true, name: "Usha Urgent" }),
    req({
      reference: "IM-SAFE03", age_minutes: 10, safety_level: "high", status: "triaged", owner: "agent@im.test", name: "Asha Verma",
      phone: "+919800001234", pincode: "110004", area: "Rashtrapati Bhawan", point: { lat: 28.6455, lon: 77.205, precision: "rough" },
      problem_summary: "Brake warning light and grinding", category_code: "brakes", category: "Brakes",
    }),
    req({
      reference: "IM-WORK04", age_minutes: 120, safety_level: "medium", status: "in_progress", owner: "agent@im.test", name: "Kiran",
      assignments: [{ id: 1, mechanic_id: 2, mechanic: "Sunita Devi", status: "accepted", offered_at: ago(100), responded_at: ago(95),
        offered_by: "agent@im.test", match: { suggested: true }, note: "" }],
    }),
    req({ reference: "IM-DONE05", age_minutes: 2000, status: "completed", name: "Closed Customer" }),
  ]; // prettier-ignore
  mechanics: Json[] = [
    mechanic(1, "Ravi Kumar", { skills: ["battery", "brakes"] }),
    mechanic(2, "Sunita Devi", { rating: 4.0, base_pincode: "110004", base_area: "Central Delhi", base_point: [28.6455, 77.205], base_precision: "rough" }),
    mechanic(3, "Mohan Lal", { on_duty: false, rating: null, acceptance_rate: null }),
  ];
  documents: Json[] = [];
  queueQueries: string[] = [];
  offers: Json[] = [];
  outcomes: Json[] = [];
  reveals: string[] = [];

  private detail(r: Req, me: { email: string; perms: Set<string> }) {
    const { owner, phone, ...rest } = r;
    const open = r.assignments.filter((a) => a.status === "offered" || a.status === "accepted").at(-1);
    return {
      ...rest,
      phone: mask(phone),
      agent: owner ? owner.split("@")[0].replace(/^\w/, (c) => c.toUpperCase()) : null,
      mechanic: (open ?? r.assignments.at(-1))?.mechanic ?? null,
      phone_revealable: owner === me.email && me.perms.has("requests.contact"),
      allowed: TRANSITIONS[r.status],
    };
  }

  private row(r: Req, me: { email: string; perms: Set<string> }) {
    const d = this.detail(r, me);
    const keep = ["id", "reference", "created_at", "age_minutes", "status", "safety_level", "urgent", "name", "phone", "area", "pincode",
      "service_type", "category_code", "category", "vehicle", "problem_summary", "agent", "mechanic", "session_id"]; // prettier-ignore
    return Object.fromEntries(Object.entries(d).filter(([k]) => keep.includes(k)));
  }

  private event(r: Req, kind: string, actor: string, data: Json = {}, note = "", from: string | null = null, to: string | null = null) {
    r.events.push({ id: r.events.length + 1000 + Math.round(Math.random() * 1e6), at: new Date().toISOString(), kind, from_status: from, to_status: to, actor, note, data });
  }

  private move(r: Req, to: string, actor: string, note = "") {
    const from = r.status;
    r.status = to;
    this.event(r, "status", actor, {}, note, from, to);
    if (["triaged", "cancelled", "escalated"].includes(to)) {
      for (const a of r.assignments) if (a.status === "offered" || a.status === "accepted") a.status = "withdrawn";
    }
  }

  private suggestions(r: Req) {
    const fits = this.mechanics.filter((m) => m.on_duty && (m.skills as string[]).includes(r.category_code ?? ""));
    return {
      category_code: r.category_code,
      point: r.point,
      notes: r.point?.precision === "rough" ? [`Pincode ${r.pincode} only has a rough location: distances can be 10-20 km off.`] : [],
      suggestions: fits.map((m, i) => ({
        mechanic_id: m.id, name: m.name, score: 0.9 - i * 0.1, distance_km: 2 + i, rating: m.rating, acceptance_rate: m.acceptance_rate,
        jobs_today: m.jobs_today, max_jobs_per_day: m.max_jobs_per_day,
        reasons: [`${2 + i} km away (straight line)`, `rated ${m.rating} of 5`, `${m.jobs_today} of ${m.max_jobs_per_day} jobs today`],
      })), // prettier-ignore
      excluded: this.mechanics
        .filter((m) => !fits.includes(m))
        .map((m) => ({ mechanic_id: m.id, name: m.name, reasons: [m.on_duty ? `no ${r.category} skill` : "off duty"] })),
    };
  }

  handle(method: string, path: string, url: URL, body: Json, perms: Set<string>, email: string, staffName: string): Result | null {
    const deny = (p: string) => (perms.has(p) ? null : { status: 403, json: { detail: "You don't have access to this" } });
    const me = { email, perms };

    // ------------------------------------------------ requests
    if (path === "/requests" && method === "GET") {
      const denied = deny("requests.read");
      if (denied) return denied;
      this.queueQueries.push(url.search);
      const p = url.searchParams;
      const view = p.get("view") ?? "open";
      const closed = (r: Req) => r.status === "completed" || r.status === "cancelled";
      let rows = this.requests.filter((r) =>
        p.get("status") ? r.status === p.get("status") : view === "open" ? !closed(r) : view === "closed" ? closed(r) : true,
      );
      if (p.get("safety")) rows = rows.filter((r) => r.safety_level === p.get("safety"));
      if (p.get("category")) rows = rows.filter((r) => r.category_code === p.get("category"));
      if (p.get("mine") === "true") rows = rows.filter((r) => r.owner === email);
      const q = p.get("q")?.toLowerCase();
      if (q) rows = rows.filter((r) => [r.reference, r.name, r.area, r.pincode].some((x) => x.toLowerCase().includes(q)));
      rows = [...rows].sort((a, b) =>
        view === "closed"
          ? b.created_at.localeCompare(a.created_at)
          : (SAFETY_ORDER[a.safety_level] ?? 3) - (SAFETY_ORDER[b.safety_level] ?? 3) ||
            Number(b.urgent) - Number(a.urgent) ||
            a.created_at.localeCompare(b.created_at),
      );
      return { status: 200, json: rows.map((r) => this.row(r, me)) };
    }
    const rm = path.match(/^\/requests\/([^/]+)(?:\/([a-z-]+))?$/);
    if (rm) {
      const r = this.requests.find((x) => x.id === rm[1]);
      if (!r) return { status: 404, json: { detail: "Request not found" } };
      const action = rm[2] ?? "";
      const done = () => ({ status: 200, json: this.detail(r, me) });
      if (method === "GET" && action === "") return deny("requests.read") ?? done();
      if (method === "GET" && action === "suggestions") return deny("requests.read") ?? { status: 200, json: this.suggestions(r) };
      if (method === "GET" && action === "faults") {
        const ranks = Object.fromEntries(r.causes.map((c) => [c.fault_key, c.rank]));
        const list = FAULTS.filter((f) => f.category_code === r.category_code || f.fault_key in ranks)
          .map((f) => ({ ...f, ai_rank: ranks[f.fault_key] ?? null }))
          .sort((a, b) => (a.ai_rank ?? 99) - (b.ai_rank ?? 99));
        return deny("requests.read") ?? { status: 200, json: list };
      }
      if (method === "POST" && action === "reveal-phone") {
        const denied = deny("requests.contact");
        if (denied) return denied;
        if (r.owner !== email) return { status: 403, json: { detail: "Only the agent assigned to this request can see the number" } };
        this.reveals.push(r.reference);
        return { status: 200, json: { phone: r.phone } };
      }
      const denied = deny("requests.update");
      if (denied) return denied;
      const conflict = (detail: string) => ({ status: 409, json: { detail } });
      if (method === "PATCH" && action === "") {
        const to = String(body.status);
        if (!TRANSITIONS[r.status].includes(to)) return conflict(`A request that is ${r.status} cannot become ${to}.`);
        if (VIA_ACTION.includes(to)) return conflict(`To make it ${to}, use its own action.`);
        if ((to === "cancelled" || to === "escalated") && !String(body.note ?? "").trim()) return conflict(`Say why it is ${to} (a short note).`);
        if (r.status === "submitted" && to === "triaged" && !r.owner) r.owner = email;
        this.move(r, to, email, String(body.note ?? ""));
        return done();
      }
      if (method === "PUT" && action === "agent") {
        r.owner = email;
        this.event(r, "agent", email, { agent: staffName });
        return done();
      }
      if (method === "POST" && action === "offer") {
        if (r.status !== "triaged") return conflict(`Only a triaged request can be offered to a mechanic (this one is ${r.status}).`);
        const m = this.mechanics.find((x) => x.id === body.mechanic_id)!;
        const suggested = this.suggestions(r).suggestions.some((s) => s.mechanic_id === m.id);
        if (!suggested && !String(body.note ?? "").trim()) {
          return { status: 422, json: { detail: `${m.name} is not a suggestion: add a note saying why you're offering anyway` } };
        }
        this.offers.push(body);
        r.assignments.push({ id: r.assignments.length + 1, mechanic_id: m.id, mechanic: m.name, status: "offered", offered_at: new Date().toISOString(),
          responded_at: null, offered_by: email, match: { suggested }, note: String(body.note ?? "") }); // prettier-ignore
        this.event(r, "offer", email, { mechanic_id: m.id });
        this.move(r, "offered", email);
        return done();
      }
      if (method === "POST" && action === "response") {
        const a = r.assignments.find((x) => x.status === "offered");
        if (r.status !== "offered" || !a) return conflict("There is no open offer to answer.");
        a.status = body.accepted ? "accepted" : "declined";
        this.event(r, "response", email, { mechanic_id: a.mechanic_id, accepted: body.accepted });
        this.move(r, body.accepted ? "accepted" : "triaged", email);
        return done();
      }
      if (method === "POST" && action === "notes") {
        r.internal_notes.push({ id: r.internal_notes.length + 1, created_at: new Date().toISOString(), author: email, text: body.text });
        return { status: 201, json: this.detail(r, me) };
      }
      if (method === "POST" && action === "outcome") {
        if (r.status !== "in_progress") return conflict(`Only a job in progress can be completed (this one is ${r.status}).`);
        const key = String(body.confirmed_fault_key);
        if (key === "other" && !String(body.other_text ?? "").trim()) return { status: 422, json: { detail: 'Say what the fault was when it is "other".' } };
        const fault = FAULTS.find((f) => f.fault_key === key);
        if (key !== "other" && !fault) return { status: 422, json: { detail: `Unknown fault ${key}` } };
        this.outcomes.push(body);
        const ranked = r.causes.map((c) => c.fault_key);
        r.outcome = {
          confirmed_fault_key: key === "other" ? null : key, confirmed_fault: fault?.name ?? null, other_text: body.other_text ?? "",
          ai_top1: ranked[0] === key, ai_top3: ranked.includes(key), ai_ranked: ranked, parts_used: body.parts_used,
          final_cost_inr: body.final_cost_inr, mechanic_notes: body.mechanic_notes, dataset_version_id: 7, mechanic_id: 2,
          recorded_by: email, recorded_at: new Date().toISOString(),
        }; // prettier-ignore
        this.event(r, "outcome", email, { confirmed_fault_key: key });
        for (const a of r.assignments) if (a.status === "accepted") a.status = "completed";
        this.move(r, "completed", email);
        return done();
      }
      return null;
    }

    // ------------------------------------------------ mechanics
    if (path === "/mechanics" && method === "GET") {
      return deny("mechanics.read") ?? { status: 200, json: this.mechanics.filter((m) => m.active || url.searchParams.get("include_inactive")).map((m) => this.mech(m, perms)) };
    }
    if (path === "/mechanics" && method === "POST") {
      const denied = deny("mechanics.manage");
      if (denied) return denied;
      if (!/^\d{6}$/.test(String(body.base_pincode)) || String(body.base_pincode).startsWith("4")) {
        return { status: 422, json: { detail: "this pincode is outside our Delhi NCR zones" } };
      }
      const m = mechanic(this.mechanics.length + 1, String(body.name), { ...body, phone: `+91${String(body.phone).replace(/\D/g, "").slice(-10)}`,
        skills: [], zones: [{ pincode: body.base_pincode, radius_km: null, center_lat: null, center_lon: null, point: [28.55, 77.2], precision: "pincode" }],
        jobs_today: 0, acceptance_rate: null, on_duty: false }); // prettier-ignore
      this.mechanics.push(m);
      return { status: 201, json: this.mech(m, perms) };
    }
    const mm = path.match(/^\/mechanics\/(\d+)(?:\/([a-z]+))?(?:\/(\d+))?$/);
    if (mm) {
      const m = this.mechanics.find((x) => x.id === Number(mm[1]));
      if (!m) return { status: 404, json: { detail: "Mechanic not found" } };
      const action = mm[2] ?? "";
      if (action === "documents") {
        const denied = deny("mechanics.documents");
        if (denied) return denied;
        if (method === "GET") return { status: 200, json: this.documents.filter((d) => d.mechanic_id === m.id) };
        if (method === "POST") {
          const d = { id: this.documents.length + 1, mechanic_id: m.id, kind: url.searchParams.get("kind"), filename: url.searchParams.get("filename"),
            content_type: "application/pdf", size: 2048, uploaded_by: email, uploaded_at: new Date().toISOString() }; // prettier-ignore
          this.documents.push(d);
          return { status: 201, json: d };
        }
        if (method === "DELETE") {
          this.documents = this.documents.filter((d) => d.id !== Number(mm[3]));
          return { status: 204 };
        }
      }
      if (method === "GET" && action === "") return deny("mechanics.read") ?? { status: 200, json: this.mech(m, perms) };
      const denied = deny("mechanics.manage");
      if (denied) return denied;
      if (method === "PUT" && action === "") Object.assign(m, body);
      if (action === "skills") m.skills = body.category_codes;
      if (action === "duty") m.on_duty = body.on_duty;
      if (action === "availability") {
        const shifts = body.shifts as { weekday: number; start_time: string; end_time: string }[];
        const overlap = shifts.some((a, i) => shifts.some((b, j) => i !== j && a.weekday === b.weekday && a.start_time < b.end_time && b.start_time < a.end_time));
        if (overlap) return { status: 422, json: { detail: "Two shifts on the same day overlap" } };
        m.shifts = shifts;
      }
      if (action === "zones") {
        m.zones = (body.zones as Json[]).map((z) => ({ ...z, point: z.pincode ? [28.6455, 77.205] : null, precision: z.pincode ? (z.pincode === "110004" ? "rough" : "pincode") : null }));
      }
      return { status: 200, json: this.mech(m, perms) };
    }
    return null;
  }

  private mech(m: Json, perms: Set<string>) {
    return { ...m, documents: perms.has("mechanics.documents") ? this.documents.filter((d) => d.mechanic_id === m.id).length : null };
  }
}
