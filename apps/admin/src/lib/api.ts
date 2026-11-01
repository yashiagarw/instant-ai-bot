// The staff API (backend/app/admin/api.py). Every call sends the staff cookie (credentials: include); it is
// HttpOnly, so this code never sees it. 401 = not signed in (the app goes to /login); 403 = no access.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong. Please try again.";
}

async function call<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const json = body !== undefined && !(body instanceof Blob);
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/admin${path}`, {
      method,
      credentials: "include",
      headers: json
        ? { "Content-Type": "application/json" }
        : body instanceof Blob
          ? { "Content-Type": body.type || "application/octet-stream" }
          : undefined,
      // A file (Blob) is sent as the request body as it is.
      body: body === undefined ? undefined : json ? JSON.stringify(body) : (body as Blob),
      signal,
      cache: "no-store",
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("We couldn't reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data && typeof data.detail === "string" ? data.detail : null;
    const fallback =
      res.status === 401
        ? "Please sign in."
        : res.status === 403
          ? "You don't have access to this."
          : res.status === 422
            ? "Please check what you entered."
            : res.status === 429
              ? "Too many attempts. Please wait a little and try again."
              : "Something went wrong. Please try again.";
    throw new ApiError(detail ?? fallback, res.status);
  }
  return data as T;
}

// ---------------------------------------------------------------- types

export type Role = "super_admin" | "content_admin" | "support_agent" | "mechanic";

export const ROLES: { value: Role; label: string; description: string }[] = [
  { value: "super_admin", label: "Super admin", description: "Everything, including staff and the audit log" },
  { value: "content_admin", label: "Content admin", description: "Diagnosis content: questions, photo labels" },
  { value: "support_agent", label: "Support agent", description: "Mechanic requests and customers" },
  { value: "mechanic", label: "Mechanic", description: "Mechanic requests, phone numbers hidden" },
];

export const roleLabel = (r: string) => ROLES.find((x) => x.value === r)?.label ?? r;

export interface Staff {
  id: string;
  email: string;
  name: string;
  roles: Role[];
  active: boolean;
  locked: boolean;
  two_factor: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Me extends Staff {
  permissions: string[];
  session_expires_at: string;
}

export interface TwoFactorSetup {
  otpauth_uri: string;
  secret: string;
  qr_svg: string;
}

export interface LoginResult {
  next: "done" | "code" | "setup";
  me: Me | null;
  setup: TwoFactorSetup | null;
}

export interface Customer {
  id: string;
  name: string | null;
  phone_masked: string;
  created_at: string;
  last_login_at: string | null;
  diagnoses: number;
  requests: number;
}

export interface AuditEntry {
  id: number;
  at: string;
  actor_id: string | null;
  actor_label: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
}

export interface AuditQuery {
  action?: string;
  entity_type?: string;
  actor?: string;
  since?: string; // ISO date-time
  until?: string;
  limit?: number;
}

// ---------------------------------------------------------------- datasets (backend/app/datasets/api.py)

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface DatasetJob {
  id: number;
  kind: "build" | "eval" | "publish" | "rollback";
  status: JobStatus;
  progress: number;
  step: string;
  log: { at: string; step: string }[];
  error: string | null;
  result: Record<string, unknown>;
  dataset_version_id: number | null;
  created_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DatasetVersion {
  id: number;
  status: "draft" | "validated" | "published" | "archived";
  origin: "import" | "upload" | "rollback";
  category_code: string | null;
  source_file_no: number | null;
  upload_name: string | null;
  created_by: string | null;
  created_at: string;
  published_at: string | null;
  published_by: string | null;
  archived_at: string | null;
  base_version_id: number | null;
  rollback_of_id: number | null;
  override_reason: string | null;
  categories: string[];
  stale: boolean;
  validated: boolean | null;
  build_error: string | null;
  losses: number;
  diff_counts: { added: number; changed: number; removed: number };
  gate: "passed" | "blocked" | null;
  gate_reasons: string[];
}

export interface Check {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
  blocking: boolean;
}

export interface Loss {
  area: string;
  category: string;
  fault_key: string;
  detail: string;
  before: number;
  after: number;
}

export interface FileReport {
  file_no: number;
  path: string;
  rows_read: number;
  imported: number;
  rejected: { row: number; id: string; reason: string }[];
  review: Record<string, number>;
  warnings: string[];
  header_row: number;
}

export interface Validation {
  error?: string;
  built_at?: string;
  categories?: string[];
  files?: number[];
  file_reports?: Record<string, FileReport>;
  checks?: Check[];
  losses?: Loss[];
  steps?: { steps: Record<string, string>; warnings: string[]; embeddings: Record<string, number> };
  warnings?: string[];
}

export interface DiffRow {
  fault_key: string;
  category: string;
  name: string;
  fields?: { field: string; before: string; after: string }[];
}

export interface Diff {
  categories?: string[];
  added?: DiffRow[];
  changed?: DiffRow[];
  removed?: DiffRow[];
  unchanged?: number;
}

export interface EvalStats {
  n: number;
  top1: number | null;
  top3: number | null;
  safety_n: number;
  safety_recall: number | null;
}

export interface EvalRun {
  version_id: number;
  cases: number;
  overall: EvalStats;
  by_category: Record<string, EvalStats>;
  skipped: string[];
}

export interface CommonStats {
  n: number;
  ranked_n: number;
  top1: number | null;
  top3: number | null;
  safety_n: number;
  safety_missed: number;
  safety_recall: number | null;
}

export interface CaseBrief {
  key: string;
  type: string;
  category: string;
  label: string;
}

export interface Comparison {
  common: number;
  live: CommonStats;
  draft: CommonStats;
  only_live: CaseBrief[];
  only_draft: CaseBrief[];
  safety_changed: { key: string; category: string; label: string; live: "fired" | "missed" | "absent"; draft: "fired" | "missed" | "absent" }[];
}

export interface Evaluation {
  comparison?: Comparison | null;
  ran_at?: string;
  scope?: { categories: string[] | null; split: string; full: boolean };
  draft?: EvalRun;
  current?: EvalRun | null;
  gate?: { ok: boolean; reasons: string[]; top3_change: number | null; safety_change: number | null; note?: string };
  skipped?: string;
}

export interface VersionDetail extends DatasetVersion {
  validation: Validation;
  diff: Diff;
  eval: Evaluation;
  publish: { blockers: string[]; gate_reasons: string[]; can_publish: boolean; can_override: boolean };
  jobs: DatasetJob[];
  editor: EditorSummary;
}

export interface DatasetCategory {
  code: string;
  name: string;
  files: { file_no: number; live_name: string }[];
  shared_with: string[];
}

export interface DatasetsOverview {
  live: DatasetVersion | null;
  versions: DatasetVersion[];
  categories: DatasetCategory[];
  active_job: DatasetJob | null;
  can_manage: boolean;
  can_override: boolean;
}

// ---------------------------------------------------------------- knowledge editors (backend/app/knowledge/edits/api.py)

export interface Draft {
  id: number;
  origin: "edit" | "upload";
  status: string;
  category_code: string | null;
  created_by: string | null;
  base_version_id: number | null;
  stale: boolean;
  edits: number;
  building: boolean;
}

export interface FaultRow {
  key: string;
  name: string;
  category: string;
  needs_review: boolean;
  safety_critical: boolean;
  lines: Record<string, number>;
  edited: boolean;
  new: boolean;
}

export interface FaultData {
  name: string;
  description: string;
  likely_fault: string;
  road_repairable: "yes" | "limited" | "no" | "unknown";
  road_repairable_text: string;
  repair_location: string;
  towing_conditions_text: string;
  repair_time_text: string;
  severity: "low" | "medium" | "high" | null;
  safety_critical: boolean;
  requires: Record<string, string | string[]>[];
  prior: number | null;
  category_code?: string | null;
}

export interface Phrase {
  key: string;
  text: string;
  language: string;
  english_gloss: string;
  source: string;
  held_out: boolean;
  reviewed_by: string | null;
  reviewed_at: string | null;
  pending_signoff: boolean;
  edit: number | null;
}

export interface SafetyData {
  risk_level: "low" | "medium" | "high";
  stop_driving_trigger: string;
  roadside_action: string;
  towing_recommendation: string;
  status: "draft" | "active_pending_signoff" | "approved" | "rejected";
  signed_off_by: string | null;
  signed_off_at: string | null;
  trigger_phrases: string[];
}

export interface SafetyRuleRow extends SafetyData {
  key: string;
  scope: string;
  category?: string | null;
  fault_key?: string | null;
  source: string;
  kind: string;
  edit: number | null;
}

export interface FaultDetail {
  key: string;
  fault: FaultData;
  fault_edit: number | null;
  items: Record<string, { key: string; lines: string[]; edit: number | null }>;
  phrases: Phrase[];
  deleted_phrases: { key: string; edit: number }[];
  images: { sha1: string; url: string; caption: string | null }[];
  images_edit: number | null;
  safety_rules: SafetyRuleRow[];
  file_no: number;
}

export interface Effect {
  fault: string;
  effect: "supports" | "rules_out";
  strength: "strong" | "moderate" | "weak";
}

export interface QuestionData {
  stage: number;
  text: string;
  status: "approved" | "draft" | "rejected";
  reviewed_by: string | null;
  reviewed_at: string | null;
  options: { label: string; not_sure: boolean; effects: Effect[] }[];
}

export interface QuestionRow extends QuestionData {
  key: string;
  pending_signoff: boolean;
  edit: number | null;
}

export interface CategoryData {
  name: string;
  kind: "diagnose" | "fast_track" | "inspect";
  beta: boolean;
  wave: number;
  filters: string[];
  config: { question_budget: number | null; stop_probability: number | null; stop_margin: number | null; min_questions: number | null };
}

export interface GroupData {
  group_type: "tile" | "emergency" | "inspection";
  label_en: string;
  label_hi: string;
  hi_reviewed: boolean;
  categories: string[];
  position: number;
  variants: Record<string, unknown>[];
}

export interface FilterData {
  fuel: string[];
  transmission: string[];
}

export interface Taxonomy {
  groups: (GroupData & { code: string; edit: number | null })[];
  categories: (CategoryData & { code: string; sources: { file: number; prefix: string }[]; edit: number | null })[];
  vehicle_filters: (FilterData & { name: string; edit: number | null })[];
}

export interface SignoffItem {
  entity: "question" | "phrase" | "safety_rule" | "image_label";
  key: string;
  category: string | null;
  text: string;
  reviewed_by: string | null;
  pending: boolean;
  edit: number | null;
}

export interface EditRow {
  id: number;
  entity: string;
  table: string;
  key: string;
  name: string;
  op: "added" | "changed" | "deleted" | "signed off";
  safety: boolean;
  status: string;
  by: string;
  at: string;
  reason: string;
  changes: { field: string; before: unknown; after: unknown }[];
}

export interface EditorSummary {
  tables: Record<string, Record<string, number>>;
  safety: { edit: number; name: string; key: string; by: string; changes: { field: string; before: unknown; after: unknown }[] }[];
  conflicts?: { edit: number; name: string; key: string; message: string }[];
  orphans?: { edit: number; name: string; key: string; message: string }[];
}

export interface SaveResult<T = unknown> {
  key: string;
  item: T | null;
  edit: { id: number; safety: boolean } | null;
  warning: string | null;
}

export interface GeneratedQuestion {
  id: number;
  created_at: string;
  category_code: string | null;
  text: string;
  options: string[];
  reason: string;
  status: "generated" | "approved" | "rejected";
  reviewed_by: string | null;
}

export interface UnlistedCar {
  id: number;
  created_at: string;
  raw_text: string;
  typed_make: string | null;
  typed_model: string | null;
  typed_year: number | null;
  fuel: string | null;
  transmission: string | null;
  price_segment: string | null;
  reviewed: boolean;
  sessions: number;
}

/** The API's media address for a picture path like /media/F08/x.png. */
export const mediaUrl = (path: string) => `${API_URL}${path}`;

function query(params: object): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------- calls

export const adminApi = {
  login: (email: string, password: string, code?: string) =>
    call<LoginResult>("POST", "/auth/login", { email, password, ...(code ? { code } : {}) }),
  confirmTwoFactor: (code: string) => call<Me>("POST", "/auth/two-factor/confirm", { code }),
  me: (signal?: AbortSignal) => call<Me>("GET", "/auth/me", undefined, signal),
  logout: () => call<void>("POST", "/auth/logout"),
  changePassword: (current_password: string, code: string, new_password: string) =>
    call<void>("POST", "/auth/password", { current_password, code, new_password }),

  staff: (signal?: AbortSignal) => call<Staff[]>("GET", "/staff", undefined, signal),
  invite: (email: string, name: string, roles: Role[]) =>
    call<{ staff: Staff; temporary_password: string }>("POST", "/staff", { email, name, roles }),
  setRoles: (id: string, roles: Role[]) => call<Staff>("PUT", `/staff/${id}/roles`, { roles }),
  deactivate: (id: string) => call<Staff>("POST", `/staff/${id}/deactivate`),
  activate: (id: string) => call<Staff>("POST", `/staff/${id}/activate`),
  unlock: (id: string) => call<Staff>("POST", `/staff/${id}/unlock`),
  resetTwoFactor: (id: string) => call<Staff>("POST", `/staff/${id}/reset-two-factor`),

  customers: (signal?: AbortSignal) => call<Customer[]>("GET", "/customers?limit=1000", undefined, signal),
  revealPhone: (id: string) => call<{ phone: string }>("POST", `/customers/${id}/reveal-phone`),

  audit: (q: AuditQuery, signal?: AbortSignal) => call<AuditEntry[]>("GET", `/audit${query(q)}`, undefined, signal),

  datasets: (signal?: AbortSignal) => call<DatasetsOverview>("GET", "/datasets", undefined, signal),
  datasetVersion: (id: number, signal?: AbortSignal) =>
    call<VersionDetail>("GET", `/datasets/versions/${id}`, undefined, signal),
  datasetJob: (id: number, signal?: AbortSignal) => call<DatasetJob>("GET", `/datasets/jobs/${id}`, undefined, signal),
  uploadDataset: (category: string, file: File, fileNo?: number) =>
    call<{ version: DatasetVersion; job: DatasetJob }>(
      "POST",
      `/datasets/uploads${query({ category, name: file.name, file_no: fileNo })}`,
      file,
    ),
  rebuildDataset: (id: number) => call<DatasetJob>("POST", `/datasets/versions/${id}/rebuild`),
  evalDataset: (id: number, full: boolean) => call<DatasetJob>("POST", `/datasets/versions/${id}/eval`, { full }),
  publishDataset: (id: number, override_reason?: string) =>
    call<DatasetJob>("POST", `/datasets/versions/${id}/publish`, override_reason ? { override_reason } : {}),
  rollbackDataset: (id: number, category?: string) =>
    call<DatasetJob>("POST", `/datasets/versions/${id}/rollback`, category ? { category } : {}),
  discardDataset: (id: number) => call<void>("DELETE", `/datasets/versions/${id}`),
  cancelJob: (id: number) => call<DatasetJob>("POST", `/datasets/jobs/${id}/cancel`),

  drafts: (signal?: AbortSignal) => call<Draft[]>("GET", "/knowledge/drafts", undefined, signal),
  startDraft: () => call<{ version_id: number; job: DatasetJob }>("POST", "/knowledge/drafts"),
  taxonomy: (v: number, signal?: AbortSignal) => call<Taxonomy>("GET", `/knowledge/versions/${v}/taxonomy`, undefined, signal),
  faults: (v: number, category?: string, signal?: AbortSignal) =>
    call<FaultRow[]>("GET", `/knowledge/versions/${v}/faults${query({ category })}`, undefined, signal),
  fault: (v: number, key: string, signal?: AbortSignal) =>
    call<FaultDetail>("GET", `/knowledge/versions/${v}/faults/${encodeURIComponent(key)}`, undefined, signal),
  questions: (v: number, category: string, signal?: AbortSignal) =>
    call<{ questions: QuestionRow[]; faults: { key: string; name: string }[] }>(
      "GET",
      `/knowledge/versions/${v}/questions${query({ category })}`,
      undefined,
      signal,
    ),
  safetyRules: (v: number, signal?: AbortSignal) => call<SafetyRuleRow[]>("GET", `/knowledge/versions/${v}/safety`, undefined, signal),
  signoffQueue: (v: number, signal?: AbortSignal) => call<SignoffItem[]>("GET", `/knowledge/versions/${v}/signoff`, undefined, signal),
  edits: (v: number, signal?: AbortSignal) =>
    call<{ edits: EditRow[]; summary: EditorSummary; conflicts: EditorSummary["conflicts"]; orphans: EditorSummary["orphans"] }>(
      "GET",
      `/knowledge/versions/${v}/edits`,
      undefined,
      signal,
    ),
  images: (fileNo?: number) => call<{ sha1: string; url: string; caption: string | null }[]>("GET", `/knowledge/images${query({ file_no: fileNo })}`),
  saveEdit: <T = unknown>(v: number, entity: string, key: string, data: unknown, reason = "") =>
    call<SaveResult<T>>("POST", `/knowledge/versions/${v}/edits`, { entity, key, data, reason }),
  signOff: (v: number, entity: string, key: string) => call<SaveResult>("POST", `/knowledge/versions/${v}/signoff`, { entity, key }),
  revertEdit: (v: number, id: number) => call<void>("DELETE", `/knowledge/versions/${v}/edits/${id}`),

  generatedQuestions: (status?: string, signal?: AbortSignal) =>
    call<GeneratedQuestion[]>("GET", `/content/generated-questions${query({ status })}`, undefined, signal),
  approveGenerated: (id: number, body: { version_id: number; category: string; stage: number; text: string; options: string[] }) =>
    call<{ question: string; version_id: number }>("POST", `/knowledge/generated-questions/${id}/approve`, body),
  rejectGenerated: (id: number) => call<GeneratedQuestion>("POST", `/content/generated-questions/${id}/review`, { decision: "rejected" }),

  unlisted: (signal?: AbortSignal) => call<UnlistedCar[]>("GET", "/vehicles/unlisted", undefined, signal),
  makes: () => call<{ name: string; models: string[] }[]>("GET", "/vehicles/makes"),
  addUnlisted: (id: number, body: unknown) => call<{ created: string[] }>("POST", `/vehicles/unlisted/${id}/add`, body),
  dismissUnlisted: (id: number) => call<{ ok: boolean }>("POST", `/vehicles/unlisted/${id}/dismiss`),
};
