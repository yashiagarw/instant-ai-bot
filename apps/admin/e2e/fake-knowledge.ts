// The /api/admin/knowledge and /api/admin/vehicles part of the fake API (see fake-admin.ts): one edit draft (v50)
// with two battery faults, a question, safety rules and sign-off items. Saves update the items and add edit rows,
// like the real API (which also validates and audits).

type Json = Record<string, unknown>;
type Result = { status: number; json?: unknown };

const NOW = "2026-11-01T10:00:00Z";
const PENDING = "claude_code (auto, pending mechanic sign-off)";

interface Edit extends Json {
  id: number;
  entity: string;
  key: string;
  name: string;
  op: string;
  safety: boolean;
  changes: { field: string; before: unknown; after: unknown }[];
}

import type { FakeParts } from "./fake-parts";

export class FakeKnowledge {
  constructor(private parts?: FakeParts) {}

  items: Record<string, Json | null> = {
    "fault:F08-BT-01": {
      name: "Weak battery", description: "Battery too weak to crank", likely_fault: "Old battery", road_repairable: "yes",
      road_repairable_text: "Yes - jump start", repair_location: "Roadside", towing_conditions_text: "", repair_time_text: "15 min",
      severity: null, safety_critical: false, requires: [], prior: null, category_code: "battery",
    },
    "fault:F08-BT-03": {
      name: "Swollen battery", description: "Case bulging", likely_fault: "Overcharging", road_repairable: "no",
      road_repairable_text: "No", repair_location: "Workshop", towing_conditions_text: "", repair_time_text: "1 h",
      severity: "high", safety_critical: true, requires: [], prior: null, category_code: "battery",
    },
    "fault_items:F08-BT-01/symptom": { lines: ["Clicking sound", "Dim lights"] },
    "safety_rule:F08-BT-03/sheet/general": {
      risk_level: "high", stop_driving_trigger: "Battery case is swollen", roadside_action: "Do not charge it",
      towing_recommendation: "Tow", status: "active_pending_signoff", signed_off_by: null, signed_off_at: null, trigger_phrases: [],
    },
    "question:battery/battery-main": {
      stage: 2, text: "What problem are you facing?", status: "approved", reviewed_by: PENDING, reviewed_at: null,
      options: [
        { label: "Car not starting", not_sure: false, effects: [{ fault: "F08-BT-01", effect: "supports", strength: "strong" }] },
        { label: "Battery looks swollen", not_sure: false, effects: [{ fault: "F08-BT-03", effect: "supports", strength: "strong" }] },
        { label: "Not sure", not_sure: true, effects: [] },
      ],
    },
  }; // prettier-ignore
  phrases: Json[] = [
    { key: "F08-BT-01|gaadi start nahi ho rahi", text: "gaadi start nahi ho rahi", language: "hinglish", english_gloss: "", source: "dataset",
      held_out: false, reviewed_by: null, reviewed_at: null, pending_signoff: false },
    { key: "F08-BT-01|battery down hai", text: "battery down hai", language: "hinglish", english_gloss: "", source: "dataset",
      held_out: true, reviewed_by: null, reviewed_at: null, pending_signoff: false },
  ]; // prettier-ignore
  edits: Edit[] = [];
  saves: Json[] = [];
  unlisted = [
    { id: 7, created_at: NOW, raw_text: "tata curvv 2025", typed_make: "Tata", typed_model: "Curvv", typed_year: 2025, fuel: "petrol",
      transmission: null, price_segment: "mid", reviewed: false, sessions: 2 },
  ]; // prettier-ignore
  added: Json[] = [];

  private editOf(entity: string, key: string) {
    return this.edits.find((e) => e.entity === entity && e.key === key)?.id ?? null;
  }

  private record(entity: string, key: string, before: Json | null, after: Json | null, op: string) {
    const fields = [...new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])].filter(
      (f) => JSON.stringify(before?.[f]) !== JSON.stringify(after?.[f]),
    );
    const existing = this.edits.find((e) => e.entity === entity && e.key === key);
    const row: Edit = {
      id: existing?.id ?? this.edits.length + 1, entity, key, name: `${entity.replace("_", " ")} ${key}`, op,
      safety: entity === "safety_rule", status: "draft", by: "content@im.test", at: NOW, reason: "", table: entity,
      changes: fields.map((f) => ({ field: f, before: before?.[f] ?? null, after: after?.[f] ?? null })),
    }; // prettier-ignore
    if (existing) Object.assign(existing, row);
    else this.edits.push(row);
    return row;
  }

  private summary() {
    const tables: Record<string, Record<string, number>> = {};
    for (const e of this.edits) (tables[e.table as string] ??= {})[e.op] = (tables[e.table as string][e.op] ?? 0) + 1;
    const safety = this.edits.filter((e) => e.safety).map((e) => ({ edit: e.id, name: e.name, key: e.key, by: e.by, changes: e.changes }));
    return { tables, safety };
  }

  private rule(key: string) {
    return { key, scope: "fault", category: "battery", fault_key: key.split("/")[0], source: "sheet", kind: "general",
      ...(this.items[`safety_rule:${key}`] as Json), edit: this.editOf("safety_rule", key) }; // prettier-ignore
  }

  handle(method: string, path: string, body: Json, perms: Set<string>): Result | null {
    if (path === "/content/generated-questions" && perms.has("content.read")) return { status: 200, json: [] };
    if (!path.startsWith("/knowledge") && !path.startsWith("/vehicles")) return null;
    if (!perms.has("content.read")) return { status: 403, json: { detail: "You don't have access to this" } };
    const write = method !== "GET";
    if (write && path.startsWith("/knowledge") && !perms.has("knowledge.edit")) return { status: 403, json: { detail: "You don't have access to this" } };
    if (write && path.startsWith("/vehicles") && !perms.has("vehicles.manage")) return { status: 403, json: { detail: "You don't have access to this" } };

    if (path === "/knowledge/drafts") {
      return { status: 200, json: [{ id: 50, origin: "edit", status: "validated", category_code: null, created_by: "content@im.test",
        base_version_id: 41, stale: false, edits: this.edits.length, building: false }] }; // prettier-ignore
    }
    const v = "/knowledge/versions/50";
    if (path === `${v}/taxonomy`) {
      return { status: 200, json: {
        groups: [{ code: "battery_dead", group_type: "tile", label_en: "Battery dead", label_hi: "बैटरी डाउन", hi_reviewed: true,
          categories: ["battery"], position: 0, variants: [], edit: null }],
        categories: [{ code: "battery", name: "Battery", kind: "diagnose", beta: false, wave: 1, filters: [], sources: [{ file: 8, prefix: "BT" }],
          config: { question_budget: null, stop_probability: null, stop_margin: null, min_questions: null }, edit: this.editOf("category", "battery") }],
        vehicle_filters: [{ name: "diesel", fuel: ["diesel"], transmission: [], edit: null }],
      } }; // prettier-ignore
    }
    if (path === `${v}/faults`) {
      return { status: 200, json: ["F08-BT-01", "F08-BT-03"].map((k) => ({ key: k, name: (this.items[`fault:${k}`] as Json).name,
        category: "battery", needs_review: false, safety_critical: k === "F08-BT-03", lines: { symptom: 2 },
        edited: this.edits.some((e) => e.key.startsWith(k)), new: false })) }; // prettier-ignore
    }
    const fault = path.match(/^\/knowledge\/versions\/50\/faults\/(.+)$/);
    if (fault) {
      const k = decodeURIComponent(fault[1]);
      const types = ["symptom", "cause", "diagnosis_step", "resolution_step", "advice", "safety", "towing_condition", "mechanic_task", "mechanic_step"];
      return { status: 200, json: {
        key: k, fault: this.items[`fault:${k}`], fault_edit: this.editOf("fault", k),
        items: Object.fromEntries(types.map((t) => [t, { key: `${k}/${t}`, lines: ((this.items[`fault_items:${k}/${t}`] as Json)?.lines as string[]) ?? [],
          edit: this.editOf("fault_items", `${k}/${t}`) }])),
        phrases: this.phrases.filter((p) => String(p.key).startsWith(`${k}|`)).map((p) => ({ ...p, edit: this.editOf("phrase", String(p.key)) })),
        deleted_phrases: [], images: [], images_edit: null, file_no: 8,
        safety_rules: k === "F08-BT-03" ? [this.rule("F08-BT-03/sheet/general")] : [],
      } }; // prettier-ignore
    }
    if (path.startsWith(`${v}/questions`)) {
      const key = "battery/battery-main";
      const q = this.items[`question:${key}`] as Json;
      return { status: 200, json: { questions: [{ key, ...q, pending_signoff: String(q.reviewed_by ?? "").includes("pending"),
        edit: this.editOf("question", key) }], faults: [{ key: "F08-BT-01", name: "Weak battery" }, { key: "F08-BT-03", name: "Swollen battery" }] } }; // prettier-ignore
    }
    if (path === `${v}/safety`) return { status: 200, json: [this.rule("F08-BT-03/sheet/general")] };
    if (path === `${v}/signoff` && method === "GET") {
      const q = this.items["question:battery/battery-main"] as Json;
      const r = this.items["safety_rule:F08-BT-03/sheet/general"] as Json;
      return { status: 200, json: [
        { entity: "question", key: "battery/battery-main", category: "battery", text: String(q.text), reviewed_by: q.reviewed_by,
          pending: String(q.reviewed_by ?? "").includes("pending"), edit: this.editOf("question", "battery/battery-main") },
        { entity: "safety_rule", key: "F08-BT-03/sheet/general", category: "battery", text: "F08-BT-03: Battery case is swollen",
          reviewed_by: r.signed_off_by, pending: r.status === "active_pending_signoff", edit: this.editOf("safety_rule", "F08-BT-03/sheet/general") },
      ] }; // prettier-ignore
    }
    if (path === `${v}/edits` && method === "GET") {
      return { status: 200, json: { edits: [...this.edits].reverse(), summary: this.summary(), conflicts: [], orphans: [] } };
    }
    if (path === `${v}/edits` && method === "POST") {
      this.saves.push(body);
      const entity = String(body.entity);
      const key = String(body.key);
      const data = body.data as Json | null;
      const fromParts = this.parts?.save(entity, key, data, "content@im.test");
      if (fromParts) return fromParts;
      if (entity === "phrase") {
        const existing = this.phrases.find((p) => p.key === key);
        if (existing?.held_out) return { status: 422, json: { detail: "held-out phrases are evaluation cases and cannot be edited" } };
        if (data === null) this.phrases = this.phrases.filter((p) => p.key !== key);
        else this.phrases.push({ key, ...data, source: "drafted", held_out: false, pending_signoff: false });
        this.record(entity, key, existing ?? null, data, data === null ? "deleted" : existing ? "changed" : "added");
        return { status: 200, json: { key, item: data, edit: { id: 1, safety: false }, warning: null } };
      }
      if (entity === "safety_rule" && data?.status === "approved" && !data.signed_off_by) {
        return { status: 422, json: { detail: "item: an approved rule needs a sign-off (name and date)" } };
      }
      const before = this.items[`${entity}:${key}`] ?? null;
      this.items[`${entity}:${key}`] = data;
      const row = this.record(entity, key, before, data, data === null ? "deleted" : before ? "changed" : "added");
      return { status: 200, json: { key, item: data, edit: { id: row.id, safety: row.safety },
        warning: row.safety ? "This changes a safety rule." : null } }; // prettier-ignore
    }
    if (path === `${v}/signoff`) {
      const entity = String(body.entity);
      const key = String(body.key);
      const before = this.items[`${entity}:${key}`] as Json;
      const after = entity === "safety_rule"
        ? { ...before, status: "approved", signed_off_by: "content@im.test", signed_off_at: NOW }
        : { ...before, reviewed_by: "content@im.test", reviewed_at: NOW };
      this.items[`${entity}:${key}`] = after;
      this.record(entity, key, before, after, "signed off");
      return { status: 200, json: { key, item: after, edit: { id: 1, safety: entity === "safety_rule" }, warning: null } };
    }
    const revert = path.match(/^\/knowledge\/versions\/50\/edits\/(\d+)$/);
    if (revert && method === "DELETE") {
      const e = this.edits.find((x) => x.id === Number(revert[1]))!;
      const restored: Json = { ...(this.items[`${e.entity}:${e.key}`] as Json) };
      for (const c of e.changes) restored[c.field] = c.before;
      this.items[`${e.entity}:${e.key}`] = restored;
      this.edits = this.edits.filter((x) => x !== e);
      return { status: 204 };
    }
    if (path === "/vehicles/unlisted") return { status: 200, json: this.unlisted };
    if (path === "/vehicles/makes") return { status: 200, json: [{ name: "Tata", models: ["Nexon", "Punch"] }] };
    const unl = path.match(/^\/vehicles\/unlisted\/(\d+)\/(add|dismiss)$/);
    if (unl) {
      this.unlisted = this.unlisted.filter((u) => u.id !== Number(unl[1]));
      if (unl[2] === "add") {
        this.added.push(body);
        return { status: 200, json: { created: [`model Tata ${body.model}`] } };
      }
      return { status: 200, json: { ok: true } };
    }
    return { status: 404, json: { detail: "Not Found" } };
  }
}
