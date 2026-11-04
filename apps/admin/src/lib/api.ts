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
  /** Embedding model of this version's search vectors (EMBEDDING_MODEL when it was built). */
  embedding_model: string;
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

export interface StepsRun {
  steps: Record<string, string>;
  warnings: string[];
  embeddings: Record<string, number>;
  edits?: { applied: number; conflicts: unknown[]; orphans: unknown[] };
}

export interface Validation {
  error?: string;
  built_at?: string;
  categories?: string[];
  files?: number[];
  file_reports?: Record<string, FileReport>;
  checks?: Check[];
  losses?: Loss[];
  steps?: StepsRun; // when the draft was built
  publish_steps?: StepsRun; // when it was published (edits saved after the build are applied here)
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
  second_look?: { count: number; items: { key: string; part: string; segment: string; price_inr: number; price_max_inr: number | null }[] };
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

// ---------------------------------------------------------------- vehicles and parts (phase 4.4 part 2)

export interface CatMake {
  id: number;
  name: string;
  aliases: string;
  edited_by: string | null;
}
export interface CatGeneration {
  id: number;
  model_id: number;
  name: string;
  year_from: number;
  year_to: number | null;
  edited_by: string | null;
}
export interface CatVariant {
  id: number;
  model_id: number;
  generation_id: number | null;
  name: string;
  fuel: string;
  transmission: string;
  engine: string;
  year_from: number;
  year_to: number | null;
  price_segment: string;
  features: Record<string, boolean>;
  edited_by: string | null;
}
export interface CatModel {
  id: number;
  make_id: number;
  name: string;
  body_type: string | null;
  aliases: string;
  edited_by: string | null;
  generations: CatGeneration[];
  variants: CatVariant[];
}
export interface Catalogue {
  makes: (CatMake & { models: CatModel[] })[];
  features: Record<string, string>;
}

export interface PartRow {
  key: string;
  description: string;
  part_type: string;
  brand: string;
  part_number: string;
  kind: string;
  prices: number;
  price_min: number | null;
  price_max: number | null;
  second_look: number;
  fits: number;
  edited: boolean;
}
export interface PartData {
  description: string;
  part_type: string;
  brand: string;
  brand_kind: "oem" | "oes" | "aftermarket" | "unspecified";
  part_number: string;
  quantity: number;
  kind: "part" | "consumable";
  segment: "budget" | "mid" | "premium" | null;
  generic: boolean;
}
export interface PriceRow {
  key: string;
  segment: string;
  source: string;
  source_ref: string;
  price_inr: number;
  price_max_inr: number | null;
  supplier: string;
  source_url: string;
  checked_on: string | null;
  verification_status: string;
  gst_included: boolean | null;
  fitting_included: boolean | null;
  model_verified: boolean;
  price_basis: string;
  note: string;
  second_look_by: string | null;
  second_look_at: string | null;
  edit: number | null;
  flagged: boolean;
  missing_source: boolean;
  part_key?: string;
  part?: string;
}
export interface FitRow {
  key: string;
  model_id: number;
  model: string;
  year_from: number | null;
  year_to: number | null;
  fuel: string | null;
  transmission: string | null;
  fit_text: string;
  verification_status: string;
  source_url: string;
  source: string;
  edit: number | null;
}
export interface Picture {
  sha1: string;
  url: string;
  caption: string | null;
}
export interface PartDetail {
  key: string;
  part: PartData;
  part_edit: number | null;
  prices: PriceRow[];
  fits: FitRow[];
  images: Picture[];
  images_edit: number | null;
}
export interface ZoneRateRow {
  key: string;
  zone: string;
  zone_label: string;
  segment: string;
  rate_min_inr: number | null;
  rate_max_inr: number | null;
  source: string;
  checked_on: string | null;
  edit: number | null;
}
export interface LabourRow {
  key: string;
  repair: string;
  segment: string;
  city: string;
  amount_inr: number;
  workshop_type: string;
  basis: string;
  status: string;
  checked_on: string | null;
  source: string;
  edit: number | null;
}
export interface ImportRow {
  line: number;
  row: Record<string, string>;
  errors: string[];
  part_key: string | null;
  flagged: boolean;
}
export interface ImportResult {
  summary: { rows: number; valid: number; errors: number; flagged: number };
  rows: ImportRow[];
}

// ---------------------------------------------------------------- mechanics and requests (phase 5.1)

/** "pincode" (its centre), "rough" (estimated: can be 10-20 km off) or "zone" (only the zone's centre is known). */
export type Precision = "pincode" | "rough" | "zone";

export interface Zone {
  pincode: string | null;
  radius_km: number | null;
  center_lat: number | null;
  center_lon: number | null;
  point: [number, number] | null;
  precision: Precision | null;
}

export interface Shift {
  weekday: number; // 0 = Monday
  start_time: string; // "09:00", India time
  end_time: string;
}

export interface Mechanic {
  id: number;
  name: string;
  phone: string;
  base_pincode: string;
  base_area: string;
  base_point: [number, number] | null;
  base_precision: Precision | null;
  rating: number | null;
  max_jobs_per_day: number;
  on_duty: boolean;
  on_duty_changed_at: string | null;
  active: boolean;
  staff_user_id: string | null;
  notes: string;
  dev_seed: boolean;
  skills: string[];
  zones: Zone[];
  shifts: Shift[];
  jobs_today: number;
  acceptance_rate: number | null;
  documents: number | null;
}

export interface MechanicInput {
  name: string;
  phone: string;
  base_pincode: string;
  base_area: string;
  rating: number | null;
  max_jobs_per_day: number;
  active: boolean;
  notes: string;
}

export type ZoneInput = Pick<Zone, "pincode" | "radius_km" | "center_lat" | "center_lon">;

export type DocumentKind = "id_proof" | "driving_licence" | "certificate" | "other";

export interface MechanicDocument {
  id: number;
  kind: DocumentKind;
  filename: string;
  content_type: string;
  size: number;
  uploaded_by: string;
  uploaded_at: string;
}

export interface CategoryOption {
  code: string;
  name: string;
  kind: string;
}

export type RequestStatus =
  | "submitted"
  | "triaged"
  | "offered"
  | "accepted"
  | "en_route"
  | "arrived"
  | "in_progress"
  | "completed"
  | "cancelled"
  | "escalated";

export type SafetyLevel = "none" | "low" | "medium" | "high";

export interface QueueRow {
  id: string;
  reference: string;
  created_at: string;
  age_minutes: number;
  status: RequestStatus;
  safety_level: SafetyLevel;
  urgent: boolean;
  name: string;
  phone: string; // always masked
  area: string;
  pincode: string;
  service_type: string;
  category_code: string | null;
  category: string | null;
  vehicle: string;
  problem_summary: string;
  agent: string | null;
  mechanic: string | null;
  session_id: string | null;
}

export interface QueueQuery {
  view?: "open" | "closed" | "all";
  status?: string;
  safety?: string;
  category?: string;
  mine?: boolean;
  q?: string;
}

export interface Assignment {
  id: number;
  mechanic_id: number;
  mechanic: string;
  status: "offered" | "accepted" | "declined" | "withdrawn" | "completed";
  offered_at: string;
  responded_at: string | null;
  offered_by: string;
  match: { suggested?: boolean; score?: number; distance_km?: number | null; reasons?: string[] };
  note: string;
}

export interface RequestEvent {
  id: number;
  at: string;
  kind: "status" | "offer" | "response" | "agent" | "outcome";
  from_status: string | null;
  to_status: string | null;
  actor: string;
  note: string;
  data: Record<string, unknown>;
}

export interface PartUsed {
  name: string;
  quantity: number;
  price_inr: number | null;
}

export interface Outcome {
  confirmed_fault_key: string | null;
  confirmed_fault: string | null;
  other_text: string;
  ai_top1: boolean | null;
  ai_top3: boolean | null;
  ai_ranked: string[];
  parts_used: PartUsed[];
  final_cost_inr: number | null;
  mechanic_notes: string;
  dataset_version_id: number | null;
  mechanic_id: number | null;
  recorded_by: string;
  recorded_at: string;
}

export interface RequestDetail extends QueueRow {
  address: string;
  preferred_time: string;
  notes_from_customer: string;
  phone_revealable: boolean;
  point: { lat: number; lon: number; precision: Precision } | null;
  causes: { rank: number; fault_key: string; name: string | null; confidence: string }[];
  allowed: RequestStatus[];
  assignments: Assignment[];
  events: RequestEvent[];
  internal_notes: { id: number; created_at: string; author: string; text: string }[];
  outcome: Outcome | null;
  notifications?: NotificationRow[];
}

/** A notification about a request (backend/app/notify): numbers masked, no message text. Read-only. */
export interface NotificationRow {
  id: number;
  created_at: string;
  event: string;
  template: string;
  language: string;
  recipient: "customer" | "mechanic" | "support";
  to: string;
  channel: "whatsapp" | "sms" | "push" | "email";
  status: "queued" | "sent" | "delivered" | "read" | "failed" | "skipped";
  attempts: number;
  provider: string | null;
  error: string | null;
  sent_at: string | null;
  previous_id: number | null;
}

export interface Suggestion {
  mechanic_id: number;
  name: string;
  score: number;
  distance_km: number | null;
  rating: number | null;
  acceptance_rate: number | null;
  jobs_today: number;
  max_jobs_per_day: number;
  reasons: string[];
}

export interface Suggestions {
  category_code: string | null;
  point: { lat: number; lon: number; precision: Precision } | null;
  notes: string[];
  suggestions: Suggestion[];
  excluded: { mechanic_id: number; name: string; reasons: string[] }[];
}

export interface FaultOption {
  fault_key: string;
  name: string;
  category_code: string;
  ai_rank: number | null;
}

export interface OutcomeInput {
  confirmed_fault_key: string;
  other_text: string;
  parts_used: PartUsed[];
  final_cost_inr: number | null;
  mechanic_notes: string;
}

// ---------------------------------------------------------------- overview and quality (backend/app/quality)

/** Without a live LLM (LLM_PROVIDER=none, or no key) only { live: false }: the pages say "LLM off". */
export type LlmUsage =
  | { live: false }
  | {
      live: true;
      calls: number;
      cost_usd: number;
      daily_cap_usd: number;
      failures: number;
      failure_rate: number | null;
      fallbacks: number;
      fallback_rate: number | null;
      by_outcome: Record<string, number>;
    };

export interface SafetyAlertCount {
  alerts: number;
  sessions: number;
  by_risk: Record<string, number>;
}

export interface UnassignedRequest {
  id: string;
  reference: string;
  status: RequestStatus;
  safety_level: SafetyLevel;
  urgent: boolean;
  age_minutes: number;
  area: string;
  pincode: string;
  category_code: string | null;
}

export interface OverviewData {
  now: string;
  day_start: string;
  requests: { total: number; by_status: Record<string, number>; unassigned_after_minutes: number; unassigned: UnassignedRequest[] } | null;
  diagnoses: { started: number; completed: number; safety_alerts: SafetyAlertCount } | null;
  llm: LlmUsage | null;
}

export interface EvalStatsRow {
  n?: number;
  ranked_n?: number;
  top1?: number | null;
  top3?: number | null;
  avg_questions?: number | null;
  safety_n?: number;
  safety_recall?: number | null;
}

export interface Accuracy {
  cases: number;
  enough: boolean;
  top1: number | null;
  top3: number | null;
}

export interface QualityData {
  days: number;
  since: string;
  eval: {
    version_id: number;
    ran_at: string;
    scope: { split?: string; categories?: string[] | null; full?: boolean } | null;
    cases: number | null;
    overall: EvalStatsRow;
    danger_missed: number | null;
    by_category: (EvalStatsRow & { category: string; name: string })[];
    real: { cases: number; overall: EvalStatsRow; by_category: (EvalStatsRow & { category: string; name: string })[]; skipped: string[] } | null;
  } | null;
  confirmed: {
    min_cases: number;
    overall: Accuracy;
    by_category: (Accuracy & { category: string; name: string })[];
    by_version: (Accuracy & { dataset_version_id: number | null })[];
  };
  confirmed_window: Accuracy;
  sessions: {
    completed: number;
    with_result: number;
    low_confidence: number;
    low_confidence_rate: number | null;
    no_match: number;
    no_match_rate: number | null;
    avg_questions: number | null;
  };
  helpful: { answers: number; helpful: number; rate: number | null };
  llm: LlmUsage;
  safety: { alerts_today: SafetyAlertCount };
}

export type ReviewKind = "negative_feedback" | "low_confidence" | "no_match";

export interface ReviewRow {
  session_id: string;
  at: string;
  vehicle: string;
  topic: string | null;
  text: string;
  top: { fault_key: string; name: string | null; confidence: string } | null;
  comment: string | null;
  feedback_source: string | null;
  golden: boolean;
}

export interface ReplayStep {
  id: number;
  at: string;
  kind: string;
  text: string;
  detail: string;
  counted: boolean;
}

export interface Replay {
  id: string;
  created_at: string;
  completed_at: string | null;
  status: string;
  vehicle: string;
  segment: string | null;
  listed_car: boolean;
  coverage_level: string | null;
  topic: string | null;
  engine_version: string;
  dataset_version_id: number | null;
  questions_answered: number;
  steps: ReplayStep[];
  results: { rank: number; fault_key: string; name: string | null; confidence: string; score: number }[];
  feedback: { at: string; source: string; helpful: boolean | null; comment: string }[];
  request: {
    reference: string;
    status: string;
    confirmed_fault_key: string | null;
    confirmed_fault: string | null;
    other_text: string;
    completed: boolean;
  } | null;
  golden: { case_id: string; added_by: string; at: string; expected: string[]; file_path: string } | null;
}

export interface GoldenInput {
  expected: string[];
  expected_alert: "high" | "medium" | "low" | "none" | null;
  confirmed_by: "mechanic" | "staff";
  note: string;
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

  bulkSignOff: (v: number, items: { entity: string; key: string }[], filter: Record<string, unknown>) =>
    call<{ signed_off: number; skipped: string[] }>("POST", `/knowledge/versions/${v}/signoff/bulk`, { items, filter }),

  catalogue: (signal?: AbortSignal) => call<Catalogue>("GET", "/vehicles/catalogue", undefined, signal),
  saveVehicle: <T>(kind: "makes" | "models" | "generations" | "variants", id: number | null, body: unknown) =>
    call<T>(id ? "PUT" : "POST", `/vehicles/${kind}${id ? `/${id}` : ""}`, body),
  deleteVehicle: (kind: "makes" | "models" | "generations" | "variants", id: number) => call<void>("DELETE", `/vehicles/${kind}/${id}`),

  parts: (v: number, signal?: AbortSignal) => call<PartRow[]>("GET", `/parts/versions/${v}/parts`, undefined, signal),
  part: (v: number, key: string, signal?: AbortSignal) =>
    call<PartDetail>("GET", `/parts/versions/${v}/parts/${key.split("/").map(encodeURIComponent).join("/")}`, undefined, signal),
  prices: (v: number, signal?: AbortSignal) => call<PriceRow[]>("GET", `/parts/versions/${v}/prices`, undefined, signal),
  labour: (v: number, signal?: AbortSignal) =>
    call<{ zones: ZoneRateRow[]; research: LabourRow[] }>("GET", `/parts/versions/${v}/labour`, undefined, signal),
  secondLook: (v: number, key: string) => call<unknown>("POST", `/parts/versions/${v}/prices/second-look`, { key }),
  importPrices: (v: number, file: Blob, commit: boolean) =>
    call<ImportResult>("POST", `/parts/versions/${v}/import${commit ? "?commit=true" : ""}`, file),
  zoneRatesYamlUrl: (v: number) => `${API_URL}/api/admin/parts/versions/${v}/zone-rates.yaml`,
  csvTemplateUrl: () => `${API_URL}/api/admin/parts/csv-template`,
  uploadPicture: (file: File, caption: string) => call<Picture>("POST", `/media/pictures${query({ caption })}`, file),

  unlisted: (signal?: AbortSignal) => call<UnlistedCar[]>("GET", "/vehicles/unlisted", undefined, signal),
  makes: () => call<{ name: string; models: string[] }[]>("GET", "/vehicles/makes"),
  addUnlisted: (id: number, body: unknown) => call<{ created: string[] }>("POST", `/vehicles/unlisted/${id}/add`, body),
  dismissUnlisted: (id: number) => call<{ ok: boolean }>("POST", `/vehicles/unlisted/${id}/dismiss`),

  /** The public category list (GET /api/categories, no sign-in): names for skills and filters. */
  categories: async (signal?: AbortSignal): Promise<CategoryOption[]> => {
    const res = await fetch(`${API_URL}/api/categories`, { signal, cache: "no-store" }).catch(() => null);
    if (!res?.ok) throw new ApiError("We couldn't load the categories. Please try again.", res?.status ?? 0);
    const data = (await res.json()) as { categories: CategoryOption[] };
    return data.categories;
  },

  mechanics: (includeInactive = false, signal?: AbortSignal) =>
    call<Mechanic[]>("GET", `/mechanics${query({ include_inactive: includeInactive || undefined })}`, undefined, signal),
  mechanic: (id: number, signal?: AbortSignal) => call<Mechanic>("GET", `/mechanics/${id}`, undefined, signal),
  saveMechanic: (id: number | null, body: MechanicInput) =>
    call<Mechanic>(id ? "PUT" : "POST", `/mechanics${id ? `/${id}` : ""}`, body),
  setSkills: (id: number, category_codes: string[]) => call<Mechanic>("PUT", `/mechanics/${id}/skills`, { category_codes }),
  setZones: (id: number, zones: ZoneInput[]) => call<Mechanic>("PUT", `/mechanics/${id}/zones`, { zones }),
  setShifts: (id: number, shifts: Shift[]) => call<Mechanic>("PUT", `/mechanics/${id}/availability`, { shifts }),
  setDuty: (id: number, on_duty: boolean) => call<Mechanic>("PUT", `/mechanics/${id}/duty`, { on_duty }),
  documents: (id: number, signal?: AbortSignal) => call<MechanicDocument[]>("GET", `/mechanics/${id}/documents`, undefined, signal),
  uploadDocument: (id: number, kind: DocumentKind, file: File) =>
    call<MechanicDocument>("POST", `/mechanics/${id}/documents${query({ kind, filename: file.name })}`, file),
  documentUrl: (id: number, doc: number) => `${API_URL}/api/admin/mechanics/${id}/documents/${doc}`,
  deleteDocument: (id: number, doc: number) => call<void>("DELETE", `/mechanics/${id}/documents/${doc}`),

  requests: (q: QueueQuery, signal?: AbortSignal) =>
    call<QueueRow[]>("GET", `/requests${query({ ...q, mine: q.mine || undefined })}`, undefined, signal),
  request: (id: string, signal?: AbortSignal) => call<RequestDetail>("GET", `/requests/${id}`, undefined, signal),
  revealRequestPhone: (id: string) => call<{ phone: string }>("POST", `/requests/${id}/reveal-phone`),
  setRequestStatus: (id: string, status: RequestStatus, note = "") => call<RequestDetail>("PATCH", `/requests/${id}`, { status, note }),
  takeRequest: (id: string) => call<RequestDetail>("PUT", `/requests/${id}/agent`, {}),
  suggestions: (id: string, signal?: AbortSignal) => call<Suggestions>("GET", `/requests/${id}/suggestions`, undefined, signal),
  faultOptions: (id: string, signal?: AbortSignal) => call<FaultOption[]>("GET", `/requests/${id}/faults`, undefined, signal),
  offer: (id: string, mechanic_id: number, note = "") => call<RequestDetail>("POST", `/requests/${id}/offer`, { mechanic_id, note }),
  mechanicAnswer: (id: string, accepted: boolean, note = "") =>
    call<RequestDetail>("POST", `/requests/${id}/response`, { accepted, note }),
  addRequestNote: (id: string, text: string) => call<RequestDetail>("POST", `/requests/${id}/notes`, { text }),
  completeJob: (id: string, body: OutcomeInput) => call<RequestDetail>("POST", `/requests/${id}/outcome`, body),

  overview: (signal?: AbortSignal) => call<OverviewData>("GET", "/overview", undefined, signal),
  quality: (days: number, signal?: AbortSignal) => call<QualityData>("GET", `/quality?days=${days}`, undefined, signal),
  reviewList: (kind: ReviewKind, days: number, signal?: AbortSignal) =>
    call<ReviewRow[]>("GET", `/quality/review${query({ kind, days })}`, undefined, signal),
  replay: (id: string, signal?: AbortSignal) => call<Replay>("GET", `/quality/sessions/${id}`, undefined, signal),
  qualityFaults: (signal?: AbortSignal) => call<Omit<FaultOption, "ai_rank">[]>("GET", "/quality/faults", undefined, signal),
  addToGolden: (id: string, body: GoldenInput) =>
    call<{ case_id: string; file_path: string; case: Record<string, unknown>; added_by: string }>("POST", `/quality/sessions/${id}/golden`, body),
};
