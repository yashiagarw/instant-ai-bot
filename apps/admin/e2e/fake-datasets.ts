// The /api/admin/datasets part of the fake API (see fake-admin.ts). A job moves on one step each time it is polled
// (queued -> running -> done), so the page's progress display is exercised. The eval always finds top-3 down 5
// points (the gate blocks), so publishing needs a super admin's written reason.

type Json = Record<string, unknown>;
type Result = { status: number; json?: unknown };

const NOW = "2026-11-01T10:00:00Z";

interface Version extends Json {
  id: number;
  status: string;
  origin: string;
  category_code: string | null;
  categories: string[];
  validation: Json;
  diff: Json;
  eval: Json;
}

interface Job extends Json {
  id: number;
  kind: string;
  status: string;
  progress: number;
  step: string;
  dataset_version_id: number;
  polls: number;
}

function version(id: number, over: Partial<Version>): Version {
  return {
    id, status: "archived", origin: "import", category_code: null, source_file_no: null, upload_name: null,
    created_by: "cli", created_at: NOW, published_at: NOW, published_by: "cli", archived_at: null, base_version_id: null,
    rollback_of_id: null, override_reason: null, embedding_model: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    categories: [], validation: {}, diff: {}, eval: {}, ...over,
  } as Version; // prettier-ignore
}

const BUILT = {
  validation: {
    categories: ["battery"], files: [8],
    checks: [
      { id: "category_rows", label: "The file has rows for battery", ok: true, detail: "battery: 43 rows", blocking: true },
      { id: "rejected_rows", label: "No rejected rows", ok: true, detail: "every row imported", blocking: true },
      { id: "nothing_lost", label: "Nothing lost from the live version", ok: true, detail: "nothing lost", blocking: true },
      { id: "embeddings", label: "Every searchable text has an embedding", ok: true, detail: "complete", blocking: true },
    ],
    file_reports: { "8": { file_no: 8, path: "battery.xlsx", rows_read: 43, imported: 43, rejected: [], review: {}, warnings: [], header_row: 4 } },
    losses: [],
    steps: { steps: { "questions load --all": "40 questions, 410 effects", "embeddings sync": "3 embedded, 120 reused" }, warnings: [], embeddings: { embedded: 3, reused: 120 } },
    warnings: [],
  },
  diff: {
    categories: ["battery"], unchanged: 40,
    added: [{ fault_key: "F08-BT-43", category: "battery", name: "Battery drains overnight" }],
    changed: [{ fault_key: "F08-BT-01", category: "battery", name: "Weak or old battery",
      fields: [{ field: "name", before: "Weak battery", after: "Weak or old battery" }] }],
    removed: [{ fault_key: "F08-BT-02", category: "battery", name: "Loose terminal" }],
  },
}; // prettier-ignore

const EVAL = {
  ran_at: NOW,
  scope: { categories: ["battery"], split: "test", full: false },
  draft: { version_id: 0, cases: 101, overall: { n: 101, top1: 0.6, top3: 0.75, safety_n: 20, safety_recall: 1 }, by_category: {}, skipped: [] },
  current: { version_id: 41, cases: 101, overall: { n: 101, top1: 0.62, top3: 0.8, safety_n: 20, safety_recall: 1 }, by_category: {}, skipped: [] },
  gate: { ok: false, top3_change: -5, safety_change: 0,
    reasons: ["Top-3 accuracy drops 5.00 points (80.00% to 75.00%); the limit is 3 points."] },
}; // prettier-ignore

export class FakeDatasets {
  versions: Version[] = [
    version(40, { categories: [] }),
    version(41, { status: "published", origin: "upload", category_code: "battery", categories: ["battery"],
      upload_name: "BATTERY v1.xlsx", created_by: "boss@im.test", published_by: "boss@im.test", base_version_id: 40 }),
  ]; // prettier-ignore
  jobs: Job[] = [];
  nextId = 42;
  publishBodies: Json[] = [];
  rollbackBodies: Json[] = [];

  private live() {
    return this.versions.find((v) => v.status === "published")!;
  }

  private out(v: Version) {
    const val = v.validation as { checks?: { ok: boolean; blocking: boolean }[]; losses?: unknown[] };
    const diff = v.diff as Record<string, unknown[] | undefined>;
    const gate = (v.eval as { gate?: { ok: boolean; reasons: string[] } }).gate;
    const rest: Json = { ...v };
    for (const k of ["validation", "diff", "eval"]) delete rest[k];
    return {
      ...rest,
      stale: false,
      validated: val.checks ? val.checks.every((c) => c.ok || !c.blocking) : null,
      build_error: null,
      losses: val.losses?.length ?? 0,
      diff_counts: { added: diff.added?.length ?? 0, changed: diff.changed?.length ?? 0, removed: diff.removed?.length ?? 0 },
      gate: gate ? (gate.ok ? "passed" : "blocked") : null,
      gate_reasons: gate?.reasons ?? [],
    };
  }

  private jobOut(j: Job) {
    const { polls: _p, ...rest } = j;
    void _p;
    return { log: [], error: null, result: {}, created_by: "staff", created_at: NOW, started_at: null, finished_at: null, ...rest };
  }

  private start(kind: string, v: Version, done: () => void): Result {
    if (this.jobs.some((j) => j.status === "queued" || j.status === "running")) {
      return { status: 409, json: { detail: "Another job is running." } };
    }
    const job: Job = { id: this.jobs.length + 1, kind, status: "queued", progress: 0, step: "waiting for the worker", dataset_version_id: v.id, polls: 0 };
    this.jobs.push(job);
    this.finishers.set(job.id, done);
    return { status: 202, json: this.jobOut(job) };
  }

  private finishers = new Map<number, () => void>();

  private advance(j: Job) {
    if (j.status === "succeeded" || j.status === "failed") return;
    j.polls += 1;
    if (j.polls === 1) Object.assign(j, { status: "running", progress: 45, step: "parts build" });
    else {
      Object.assign(j, { status: "succeeded", progress: 100, step: "done" });
      this.finishers.get(j.id)?.();
    }
  }

  private switchTo(v: Version, by: string) {
    const old = this.live();
    old.status = "archived";
    Object.assign(v, { status: "published", published_at: NOW, published_by: by });
    v.validation = { ...v.validation, publish_steps: { steps: { "editor edits apply": "2 edits applied, 0 conflicts, 0 not applied" }, warnings: [], embeddings: {} } };
  }

  handle(method: string, path: string, url: URL, body: Json, perms: Set<string>, me: string): Result | null {
    if (!path.startsWith("/datasets")) return null;
    const need = (p: string) => (perms.has(p) ? null : { status: 403, json: { detail: "You don't have access to this" } });
    const denied = need("content.read");
    if (denied) return denied;

    if (path === "/datasets" && method === "GET") {
      const active = this.jobs.find((j) => j.status === "queued" || j.status === "running");
      return { status: 200, json: {
        live: this.out(this.live()), versions: [...this.versions].reverse().map((v) => this.out(v)),
        categories: [
          { code: "battery", name: "Battery dead / weak", files: [{ file_no: 8, live_name: "BATTERY v1.xlsx" }], shared_with: [] },
          { code: "self_start", name: "Self start", files: [{ file_no: 7, live_name: "SELF START.xlsx" }], shared_with: ["stuck"] },
        ],
        active_job: active ? this.jobOut(active) : null,
        can_manage: perms.has("datasets.manage"), can_override: perms.has("datasets.override"),
      } }; // prettier-ignore
    }
    const job = path.match(/^\/datasets\/jobs\/(\d+)$/);
    if (job) {
      const j = this.jobs.find((x) => x.id === Number(job[1]))!;
      this.advance(j);
      return { status: 200, json: this.jobOut(j) };
    }
    const detail = path.match(/^\/datasets\/versions\/(\d+)$/);
    if (detail && method === "GET") {
      const v = this.versions.find((x) => x.id === Number(detail[1]))!;
      const reasons = ((v.eval as { gate?: { reasons: string[] } }).gate?.reasons ?? []) as string[];
      const validated = v.status === "validated";
      const blockers = !validated
        ? ["Only a validated draft can be published."]
        : Object.keys(v.eval).length
          ? []
          : ["Run the evaluation on this draft first."];
      return { status: 200, json: {
        ...this.out(v), validation: v.validation, diff: v.diff, eval: v.eval,
        publish: { blockers, gate_reasons: reasons, can_override: perms.has("datasets.override"),
          can_publish: validated && !blockers.length && (!reasons.length || perms.has("datasets.override")) },
        jobs: this.jobs.filter((j) => j.dataset_version_id === v.id).reverse().map((j) => this.jobOut(j)),
        editor: { tables: {}, safety: [], conflicts: [], orphans: [], second_look: { count: 0, items: [] } },
      } }; // prettier-ignore
    }

    const manage = need("datasets.manage");
    if (manage) return manage;
    if (path === "/datasets/uploads" && method === "POST") {
      const v = version(this.nextId++, {
        status: "draft", origin: "upload", category_code: url.searchParams.get("category"),
        categories: [url.searchParams.get("category") ?? ""], upload_name: url.searchParams.get("name"), created_by: me,
        published_at: null, published_by: null, base_version_id: this.live().id,
      }); // prettier-ignore
      this.versions.push(v);
      const r = this.start("build", v, () => Object.assign(v, { status: "validated", ...structuredClone(BUILT) }));
      return r.status === 202 ? { status: 202, json: { version: this.out(v), job: r.json } } : r;
    }
    const action = path.match(/^\/datasets\/versions\/(\d+)\/(eval|publish|rollback|rebuild)$/);
    if (action) {
      const v = this.versions.find((x) => x.id === Number(action[1]))!;
      if (action[2] === "eval") {
        return this.start("eval", v, () => (v.eval = { ...structuredClone(EVAL), draft: { ...EVAL.draft, version_id: v.id } }));
      }
      if (action[2] === "publish") {
        this.publishBodies.push(body);
        const gate = (v.eval as { gate?: { ok: boolean } }).gate;
        const reason = String(body.override_reason ?? "").trim();
        if (gate && !gate.ok) {
          if (!reason) return { status: 409, json: { detail: "Publishing is blocked." } };
          if (!perms.has("datasets.override")) return { status: 403, json: { detail: "Only a super admin can override the eval gate." } };
        }
        return this.start("publish", v, () => {
          this.switchTo(v, me);
          v.override_reason = reason || null;
        });
      }
      if (action[2] === "rollback") {
        this.rollbackBodies.push(body);
        const category = String(body.category ?? v.category_code ?? "");
        return this.start("rollback", v, () => {
          const n = version(this.nextId++, {
            origin: "rollback", category_code: category, categories: [category], rollback_of_id: v.id,
            base_version_id: this.live().id, created_by: me, ...structuredClone(BUILT),
          }); // prettier-ignore
          this.versions.push(n);
          this.switchTo(n, me);
        });
      }
    }
    if (detail && method === "DELETE") {
      this.versions = this.versions.filter((x) => x.id !== Number(detail[1]));
      return { status: 204 };
    }
    return { status: 404, json: { detail: "Not Found" } };
  }
}
