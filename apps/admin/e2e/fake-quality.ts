// The /api/admin/overview and /api/admin/quality part of the fake API (see fake-admin.ts). Mirrors what the pages
// rely on (backend/app/quality): overview parts by permission, "LLM off" ({ live: false }) when no LLM is used, the
// 30-case rule on confirmed accuracy, masked replays and the golden-set rules (a fault or an alert; once per session).

type Json = Record<string, unknown>;
type Result = { status: number; json?: unknown };

const NOW = new Date().toISOString();
const ago = (min: number) => new Date(Date.now() - min * 60_000).toISOString();

export const SESSION = "22222222-0000-4000-8000-000000000001";
export const NO_MATCH = "22222222-0000-4000-8000-000000000002";

export class FakeQuality {
  llm: Json = { live: false };
  real: Json | null = null;
  golden: { id: string; body: Json }[] = [];
  qualityQueries: string[] = [];

  overview(perms: Set<string>) {
    return {
      now: NOW,
      day_start: ago(600),
      requests: perms.has("requests.read")
        ? {
            total: 5, by_status: { submitted: 3, triaged: 1, completed: 1 }, unassigned_after_minutes: 10,
            unassigned: [
              { id: "11111111-0000-4000-8000-000000000003", reference: "IM-SAFE03", status: "submitted", safety_level: "high",
                urgent: false, age_minutes: 25, area: "Rashtrapati Bhawan", pincode: "110004", category_code: "brakes" },
              { id: "11111111-0000-4000-8000-000000000002", reference: "IM-URG002", status: "submitted", safety_level: "none",
                urgent: true, age_minutes: 40, area: "Malviya Nagar", pincode: "110017", category_code: "battery" },
            ],
          }
        : null, // prettier-ignore
      diagnoses: perms.has("quality.read") ? { started: 12, completed: 9, safety_alerts: { alerts: 2, sessions: 2, by_risk: { high: 1, medium: 1 } } } : null,
      llm: perms.has("quality.read") ? this.llm : null,
    };
  }

  quality(days: number) {
    const acc = (cases: number, top1: number, top3: number) =>
      cases >= 30 ? { cases, enough: true, top1, top3 } : { cases, enough: false, top1: null, top3: null };
    return {
      days, since: ago(days * 1440),
      eval: {
        version_id: 7, ran_at: ago(2000), scope: { split: "test", categories: null, full: false }, cases: 400,
        overall: { n: 400, ranked_n: 360, top1: 0.54, top3: 0.65, safety_n: 40, safety_recall: 0.975 }, danger_missed: 1,
        by_category: [
          { category: "battery", name: "Battery", n: 120, ranked_n: 110, top1: 0.6, top3: 0.72, safety_n: 10, safety_recall: 1 },
          { category: "brakes", name: "Brakes", n: 90, ranked_n: 80, top1: 0.5, top3: 0.61, safety_n: 30, safety_recall: 0.9667 },
        ],
        real: this.real,
      },
      confirmed: {
        min_cases: 30,
        overall: acc(40, 0.55, 0.8),
        by_category: [{ category: "battery", name: "Battery", ...acc(32, 0.5625, 0.8125) }, { category: "brakes", name: "Brakes", ...acc(8, 0, 0) }],
        by_version: [{ dataset_version_id: 7, ...acc(40, 0.55, 0.8) }],
      },
      confirmed_window: acc(12, 0, 0),
      sessions: { completed: 50, with_result: 46, low_confidence: 9, low_confidence_rate: 0.1957, no_match: 4, no_match_rate: 0.08, avg_questions: 3.4 },
      helpful: { answers: 20, helpful: 15, rate: 0.75 },
      llm: this.llm,
      safety: { alerts_today: { alerts: 2, sessions: 2, by_risk: { high: 1, medium: 1 } } },
    }; // prettier-ignore
  }

  review(kind: string) {
    const row = (id: string, over: Json) => ({ session_id: id, at: ago(90), vehicle: "Maruti Suzuki Swift petrol", topic: "Battery",
      text: "car not starting, call [PHONE]", top: { fault_key: "F08-BT-01", name: "Weak battery", confidence: "low" }, comment: null,
      feedback_source: null, golden: this.golden.some((g) => g.id === id), ...over }); // prettier-ignore
    if (kind === "negative_feedback") return [row(SESSION, { comment: "wrong answer, ring [PHONE]", feedback_source: "customer" })];
    if (kind === "low_confidence") return [row(SESSION, {})];
    return [row(NO_MATCH, { top: null, text: "weird noise" })];
  }

  replay(id: string) {
    const added = this.golden.find((g) => g.id === id);
    return {
      id, created_at: ago(100), completed_at: ago(95), status: "completed", vehicle: "Maruti Suzuki Swift petrol", segment: "budget",
      listed_car: true, coverage_level: "segment_estimate", topic: "battery", engine_version: "2.3.0", dataset_version_id: 7,
      questions_answered: 1,
      steps: [
        { id: 1, at: ago(100), kind: "session_started", text: "Started", detail: "battery", counted: true },
        { id: 2, at: ago(100), kind: "free_text", text: "car not starting, call [PHONE]", detail: "first words", counted: true },
        { id: 3, at: ago(99), kind: "question_asked", text: "What problem are you facing?", detail: "", counted: true },
        { id: 4, at: ago(98), kind: "answer_given", text: "Battery looks swollen", detail: "", counted: false },
        { id: 5, at: ago(98), kind: "answer_undone", text: "Took back the last answer", detail: "", counted: true },
        { id: 6, at: ago(97), kind: "answer_given", text: "Car not starting", detail: "", counted: true },
        { id: 7, at: ago(95), kind: "result_computed", text: "Result: F08-BT-01", detail: "", counted: true },
      ],
      results: id === NO_MATCH ? [] : [{ rank: 1, fault_key: "F08-BT-01", name: "Weak battery", confidence: "low", score: 0.4 }],
      feedback: [{ at: ago(90), source: "customer", helpful: false, comment: "wrong answer, ring [PHONE]" }],
      request: id === SESSION ? { reference: "IM-GOLD01", status: "completed", confirmed_fault_key: "F08-BT-02",
        confirmed_fault: "Loose battery terminal", other_text: "", completed: true } : null,
      golden: added ? { case_id: "platform-abc123def456", added_by: "content@im.test", at: NOW, expected: added.body.expected,
        file_path: "data/eval/golden/real_cases/platform-abc123def456.yaml" } : null,
    }; // prettier-ignore
  }

  handle(method: string, path: string, url: URL, body: Json, perms: Set<string>): Result | null {
    const deny = (p: string) => (perms.has(p) ? null : { status: 403, json: { detail: "You don't have access to this" } });
    if (path === "/overview") return { status: 200, json: this.overview(perms) };
    if (path === "/quality") {
      this.qualityQueries.push(url.search);
      return deny("quality.read") ?? { status: 200, json: this.quality(Number(url.searchParams.get("days") ?? 30)) };
    }
    if (path === "/quality/review") return deny("quality.read") ?? { status: 200, json: this.review(url.searchParams.get("kind") ?? "") };
    if (path === "/quality/faults") {
      return deny("quality.read") ?? { status: 200, json: [
        { fault_key: "F08-BT-01", name: "Weak battery", category_code: "battery" },
        { fault_key: "F08-BT-02", name: "Loose battery terminal", category_code: "battery" },
        { fault_key: "F11-BR-01", name: "Worn brake pads", category_code: "brakes" },
      ] }; // prettier-ignore
    }
    const m = path.match(/^\/quality\/sessions\/([^/]+)(\/golden)?$/);
    if (m && !m[2]) return deny("quality.read") ?? { status: 200, json: this.replay(m[1]) };
    if (m && method === "POST") {
      const denied = deny("quality.golden");
      if (denied) return denied;
      if (this.golden.some((g) => g.id === m[1])) return { status: 409, json: { detail: "This session is in the golden set already." } };
      if (!(body.expected as string[]).length && !body.expected_alert) {
        return { status: 422, json: { detail: "Give the right fault, or the safety alert the case should show." } };
      }
      this.golden.push({ id: m[1], body });
      return { status: 201, json: { case_id: "platform-abc123def456", file_path: "data/eval/golden/real_cases/platform-abc123def456.yaml",
        case: {}, added_by: "content@im.test" } }; // prettier-ignore
    }
    return null;
  }
}
