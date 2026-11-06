// Typed client for the FastAPI backend (backend/app/vehicles/api.py, backend/app/diagnosis/api.py).

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Fuel = "petrol" | "diesel" | "cng" | "hybrid" | "ev";
export type Transmission = "mt" | "amt" | "cvt" | "dct" | "at";
export type PriceSegment = "budget" | "mid" | "premium";

export interface Make {
  id: number;
  name: string;
}

export interface Model {
  id: number;
  make_id: number;
  name: string;
  body_type: string | null;
}

export interface Variant {
  id: number;
  model_id: number;
  name: string;
  fuel: Fuel;
  transmission: Transmission;
  engine: string;
  year_from: number;
  year_to: number | null;
  price_segment: PriceSegment;
}

export interface SearchHit {
  variant_id: number;
  make: string;
  model: string;
  model_id: number;
  variant: string;
  fuel: Fuel;
  transmission: Transmission;
  year_from: number;
  year_to: number | null;
  price_segment: PriceSegment;
  score: number;
}

export interface SearchResult {
  query: string;
  year_matched: boolean;
  results: SearchHit[];
}

export interface Category {
  code: string;
  name: string;
  kind: "diagnose" | "fast_track" | "inspect";
  beta: boolean;
  has_questions: boolean;
}

export interface Topic {
  code: string;
  type: "tile" | "emergency" | "inspection";
  label: string;
  label_hi: string;
  mode: "diagnose" | "fast_track" | "inspect";
  categories: string[];
  beta: boolean;
}

export interface CategoriesResult {
  categories: Category[];
  topics: Topic[];
}

/** An error with a message that can be shown to the customer as it is. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { signal });
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function put<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function del<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "DELETE",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    // credentials: the login and anonymous cookies (HttpOnly, SameSite=Lax) go to the API, which allows only WEB_ORIGIN.
    res = await fetch(`${API_URL}/api${path}`, {
      ...init,
      credentials: "include",
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("We couldn't reach our server. Check your internet connection and try again.");
  }
  if (res.status === 429) {
    const detail = await res
      .json()
      .then((b: { detail?: unknown }) => b.detail)
      .catch(() => null);
    throw new ApiError(typeof detail === "string" ? detail : "Too many requests. Please wait a moment and try again.", 429);
  }
  if (res.status === 401) throw new ApiError("Please log in to see this.", 401);
  if (res.status === 204) return undefined as T;
  if (res.status === 404) throw new ApiError("We couldn't find that. Please go back and pick again.", 404);
  if (res.status === 409 || res.status === 503) {
    // A plain sentence from the API ("You can add up to 5 photos…", "We couldn't reach our photo storage…").
    const detail = await res
      .json()
      .then((b: { detail?: unknown }) => b.detail)
      .catch(() => null);
    if (typeof detail === "string") throw new ApiError(detail, res.status);
    if (res.status === 409) throw new ApiError("This step has already moved on. Please refresh the page.", 409);
  }
  if (res.status === 422 || res.status === 400) {
    // Plain-sentence reasons from the API (for example "enter a 6-digit pincode") are shown as they are.
    const detail = await res
      .json()
      .then((b: { detail?: unknown }) => b.detail)
      .catch(() => null);
    const message =
      typeof detail === "string"
        ? detail.charAt(0).toUpperCase() + detail.slice(1)
        : "Something in your answer didn't look right. Please check and try again.";
    throw new ApiError(message, res.status);
  }
  if (!res.ok) throw new ApiError("Something went wrong on our side. Please try again.", res.status);
  return (await res.json()) as T;
}

/** Which car the topics are for: a catalogue variant, or what is known about an unlisted car. */
export type CarFilter = { variant_id: number } | { fuel?: Fuel | null; transmission?: Transmission | null };

function carQuery(car?: CarFilter): string {
  if (!car) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(car)) if (v !== null && v !== undefined) params.set(k, String(v));
  const q = params.toString();
  return q ? `?${q}` : "";
}

export const api = {
  categories: (signal?: AbortSignal, car?: CarFilter) => get<CategoriesResult>(`/categories${carQuery(car)}`, signal),
  createSession: (body: SessionCreate) => post<SessionOut>("/diagnosis/sessions", body),
  session: (id: string, signal?: AbortSignal) => get<SessionState>(`/diagnosis/sessions/${id}`, signal),
  answer: (id: string, question_id: number | string, option_id: number | string) =>
    post<AnswerOut>(`/diagnosis/sessions/${id}/answers`, { question_id, option_id }),
  undo: (id: string) => post<AnswerOut>(`/diagnosis/sessions/${id}/answers/undo`),
  message: (id: string, text: string) => post<MessageOut>(`/diagnosis/sessions/${id}/messages`, { text }),
  undoMessage: (id: string) => post<MessageUndoOut>(`/diagnosis/sessions/${id}/messages/undo`),
  result: (id: string, signal?: AbortSignal) => get<ResultOut>(`/diagnosis/sessions/${id}/result`, signal),
  requestConfig: (signal?: AbortSignal) => get<RequestConfig>("/service-requests/config", signal),
  createRequest: (body: ServiceRequestIn) => post<ServiceRequestOut>("/service-requests", body),
  feedback: (id: string, helpful: boolean, comment?: string) =>
    post<{ id: number }>(`/diagnosis/sessions/${id}/feedback`, { helpful, comment: comment || null }),
  makes: (signal?: AbortSignal) => get<Make[]>("/vehicles/makes", signal),
  models: (makeId: number, signal?: AbortSignal) => get<Model[]>(`/vehicles/makes/${makeId}/models`, signal),
  variants: (modelId: number, signal?: AbortSignal) =>
    get<Variant[]>(`/vehicles/models/${modelId}/variants`, signal),
  search: (q: string, signal?: AbortSignal) =>
    get<SearchResult>(`/vehicles/search?q=${encodeURIComponent(q)}&limit=8`, signal),
};

export function errorMessage(e: unknown): string {
  return e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
}

// ---------------------------------------------------------------- diagnosis sessions

export type CoverageLevel = "part_fit_verified" | "segment_estimate" | "general_guidance";
export type Mode = "diagnose" | "fast_track" | "inspect" | "suggest";

export interface SessionCreate {
  vehicle: { variant_id: number } | { unlisted: Record<string, unknown> };
  topic_id?: string | null;
  category_ids?: string[];
  text?: string;
}

export interface Option {
  id: number | string;
  label: string;
  not_sure: boolean;
}

export interface Question {
  id: number | string;
  text: string;
  options: Option[];
  category: string | null;
  phrased?: boolean;
}

export interface SafetyAlert {
  rule_id: number;
  risk: "low" | "medium" | "high";
  reason: string;
  source: "answer" | "text" | "likely" | "photo";
  roadside_action: string;
  stop_driving_trigger: string;
  towing: string;
  fault_key: string | null;
}

export interface Progress {
  question_number: number;
  questions_about: number;
}

export interface SessionOut {
  session_id: string;
  status: "in_progress" | "completed";
  mode: Mode;
  coverage_level: CoverageLevel;
  safety_alerts: SafetyAlert[];
  question: Question | null;
  done: boolean;
  safety_tips: string[];
  actions: string[];
  suggested_categories: string[];
  progress: Progress;
  disclaimer: string;
}

export interface VehicleSummary {
  label: string;
  listed: boolean;
  fuel: Fuel | null;
  transmission: Transmission | null;
  price_segment: PriceSegment | null;
  /** Catalogue variant (null for an unlisted car): decides which parts fit. */
  variant_id?: number | null;
}

export interface AnswerOut {
  session_id: string;
  status: "in_progress" | "completed";
  question: Question | null;
  done: boolean;
  new_safety_alerts: SafetyAlert[];
  safety_alerts: SafetyAlert[];
  coverage_level: CoverageLevel;
  mode: Mode;
  progress: Progress;
  previous_option_id?: number | string | null;
}

export interface Understood {
  source: "llm" | "fallback";
  symptoms: string[];
  /** What we took from the message, for the "We understood: ..." chip. Empty: added to the description. */
  items: string[];
  answered_question: boolean;
}

export interface MessageOut extends AnswerOut {
  understood: Understood;
}

export interface MessageUndoOut extends AnswerOut {
  /** The message that was taken back, to edit and send again. */
  text: string;
}

export interface SessionState extends AnswerOut {
  vehicle: VehicleSummary;
  topic: string | null;
}

export interface Cost {
  segment: PriceSegment;
  display: "amount" | "range" | "text" | "on_inspection";
  amount: number | null;
  min: number | null;
  max: number | null;
  text: string | null;
  approx_label: string | null;
  checked_on: string | null;
  is_approx: boolean;
  labour: number | null;
  labour_text: string | null;
}

export interface Media {
  file: string;
  caption: string | null;
  image_code: string | null;
  role: "main" | "also";
  start_time: number | null;
  estimated_repair_time: string;
}

export type Confidence = "high" | "medium" | "low";

export interface Evidence {
  kind: "said" | "symptom" | "main" | "answer" | "against" | "lacks";
  text: string;
  supports: boolean;
}

export interface RankedFault {
  rank: number;
  fault_key: string;
  name: string;
  category: string;
  score: number;
  confidence: Confidence;
  confidence_reason: string;
  evidence: string[];
  evidence_items: Evidence[];
  diagnostic_steps: string[];
  what_you_can_do: string[];
  what_the_mechanic_will_do: string[];
  cost: Cost | null;
  repair_time: string;
  media: Media[];
}

export type RoadsideVerdict = "do_not_drive" | "roadside_fix_possible" | "roadside_limited" | "workshop" | "unknown";

export interface ResultOut {
  session_id: string;
  status: "in_progress" | "completed";
  mode: Mode;
  vehicle: VehicleSummary;
  topic: string | null;
  engine_version: string;
  coverage_level: CoverageLevel;
  stop_reason: string | null;
  ranked: RankedFault[];
  safety_alerts: SafetyAlert[];
  roadside: { verdict: RoadsideVerdict; text: string; towing: string };
  safety_tips: string[];
  uncertainty: { code: "two_equally_likely" | "no_known_pattern"; message: string }[];
  /** If this doesn't fix it: next causes, related problems, then a full inspection. */
  if_not_fixed: string[];
  actions: string[];
  disclaimer: string;
  created_at: string;
  completed_at: string | null;
  answers: { question: string; answer: string; asked_at: string | null; answered_at: string }[];
}

export interface Explanation {
  fault_key: string;
  text: string;
  source: "template" | "llm";
}

/** Read the explanations stream (server-sent events): each `explanation` event is passed to `onExplanation` (a
 * later one for the same cause replaces the template); resolves on `done` or when the stream ends. */
export async function streamExplanations(
  id: string,
  onExplanation: (e: Explanation) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/diagnosis/sessions/${id}/explanations`, {
    headers: { Accept: "text/event-stream" },
    credentials: "include",
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError("We couldn't load the explanations.", res.status);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const fields = Object.fromEntries(
        block.split("\n").map((line) => [line.slice(0, line.indexOf(":")), line.slice(line.indexOf(":") + 1).trim()]),
      );
      if (fields.event === "done") return;
      if (fields.event === "explanation" && fields.data) onExplanation(JSON.parse(fields.data) as Explanation);
    }
    if (done) return;
  }
}

/** URL of a fault picture (served by the API at /media). */
export function mediaUrl(file: string): string {
  return `${API_URL}/media/${file.split("/").map(encodeURIComponent).join("/")}`;
}

// ---------------------------------------------------------------- Request a Mechanic

export type ServiceType = "at_location" | "tow" | "workshop";

export interface RequestConfig {
  consent_version: string;
  consent_text: string;
  helpline_number: string;
  preferred_times: { value: string; label: string }[];
  whatsapp_consent_version: string;
  whatsapp_consent_text: string;
}

export interface ServiceRequestIn {
  session_id: string | null;
  name: string;
  phone: string;
  service_type: ServiceType;
  area: string;
  pincode: string;
  address: string;
  preferred_time: string;
  notes: string;
  consent: boolean;
  consent_text_version: string;
  whatsapp_optin?: boolean;
  whatsapp_consent_version?: string | null;
}

export interface ServiceRequestOut {
  id: string;
  reference: string;
  status: string;
  urgent: boolean;
  created_at: string;
  helpline_number: string;
  next_steps: string[];
}

// ---------------------------------------------------------------- Parts and estimates (backend/app/parts, app/estimates)

export type FitStatus = "listed" | "confirm_fit" | "not_verified";
export type BrandKind = "oem" | "oes" | "aftermarket" | "unspecified";
export type Verification = "checked" | "listed_recheck" | "approx";

export interface PartPrice {
  segment: PriceSegment;
  price_inr: number;
  price_max_inr: number | null;
  approx_label: string;
  verification: Verification;
  checked_on: string | null;
  model_verified: boolean;
  price_basis: string | null;
  gst_text: string | null;
  gst_included: boolean | null;
  fitting_included: boolean | null;
  supplier: string | null;
  source_url: string | null;
  note: string | null;
}

export interface Part {
  id: number;
  name: string;
  part_type: string;
  brand: { name: string; kind: BrandKind } | null;
  part_number: string | null;
  quantity: number;
  generic: boolean;
  fit: { status: FitStatus; label: string };
  listed_for: string[];
  in_total: boolean | null;
  prices: PartPrice[];
  images: { file: string; caption: string | null; image_type: string }[];
}

export interface PartDetail extends Part {
  compatibility: {
    make: string;
    model: string;
    year_from: number | null;
    year_to: number | null;
    fuel: Fuel | null;
    transmission: Transmission | null;
    status: "listed" | "confirm_fit";
  }[];
  faults: { fault_key: string; name: string; segment: PriceSegment }[];
}

export interface PartsVehicle {
  variant_id: number;
  name: string;
  fuel: Fuel;
  transmission: Transmission;
  price_segment: PriceSegment;
}

export interface FaultParts {
  fault_key: string;
  requested_key: string;
  fault_name: string;
  vehicle: PartsVehicle | null;
  segment: PriceSegment | null;
  coverage_level: CoverageLevel;
  parts: Part[];
  disclaimer: string;
}

export interface PartCompare {
  vehicle: PartsVehicle | null;
  parts: PartDetail[];
  disclaimer: string;
}

export interface Range {
  low: number;
  high: number;
}

export interface EstimateInput {
  kind: "part" | "consumable" | "labour" | "service";
  name: string;
  low: number;
  high: number;
  source: string;
  checked_on: string | null;
  verified: boolean;
  stale: boolean;
  note: string;
}

export interface FaultEstimate {
  rank: number;
  fault_key: string;
  fault_name: string;
  status: "ok" | "not_enough_data";
  reasons: string[];
  parts: Range | null;
  consumables: Range | null;
  labour: Range | null;
  total: Range | null;
  parts_basis: "itemised" | "sheet_parts_total" | "sheet_total_minus_labour" | "none" | "";
  labour_basis: "zone_rate" | "metro_estimate" | "none" | "";
  inputs: EstimateInput[];
  flags: { needs_check: boolean; stale_inputs: string[]; unverified_inputs: string[] } | null;
  last_updated: string | null;
  oldest_input: string | null;
}

export type ZoneCode = "delhi" | "noida" | "gurugram" | "ghaziabad" | "faridabad";

export interface Estimates {
  session_id: string;
  segment: PriceSegment | null;
  zone: {
    code: ZoneCode | null;
    label: string | null;
    source: "zone" | "pincode" | "service_request" | "none";
    note: string;
    choices: { code: ZoneCode; label: string }[];
  };
  estimates: FaultEstimate[];
  source_of_truth: string;
  disclaimer: string;
}

/** Where the customer is: a zone, a pincode, or nothing chosen (Delhi NCR metro estimate). */
export type Area = { zone: ZoneCode } | { pincode: string } | null;

function query(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const partsApi = {
  estimates: (sessionId: string, area: Area, signal?: AbortSignal) =>
    get<Estimates>(`/estimates${query({ session_id: sessionId, ...(area ?? {}) })}`, signal),
  faultParts: (key: string, car: { variant_id?: number | null; segment?: PriceSegment | null }, signal?: AbortSignal) =>
    get<FaultParts>(
      `/faults/${encodeURIComponent(key)}/parts${query(car.variant_id ? { variant_id: car.variant_id } : { segment: car.segment })}`,
      signal,
    ),
  part: (id: number, variantId: number | null, signal?: AbortSignal) =>
    get<PartDetail>(`/parts/${id}${query({ variant_id: variantId })}`, signal),
  compare: (ids: number[], variantId: number | null, signal?: AbortSignal) =>
    get<PartCompare>(`/parts/compare${query({ ids: ids.join(","), variant_id: variantId })}`, signal),
};

// ---------------------------------------------------------------- Accounts (backend/app/accounts)

export interface User {
  id: string;
  phone_masked: string;
  name: string | null;
  created_at: string;
}

export interface Me {
  user: User;
  vehicles: number;
  sessions: number;
  requests: number;
}

export interface SavedCar {
  id: number;
  label: string;
  variant_id: number | null;
  created_at: string;
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  status: "in_progress" | "completed" | "abandoned";
  vehicle: string;
  topic: string | null;
  top_cause: string | null;
}

export interface RequestSummary {
  id: string;
  reference: string;
  created_at: string;
  status: string;
  status_label: string;
  urgent: boolean;
  vehicle: string;
  problem_summary: string;
}

export interface TimelineStep {
  key: string;
  label: string;
  state: "done" | "current" | "upcoming" | "cancelled";
  at: string | null;
}

export interface RequestDetail extends RequestSummary {
  service_type: ServiceType;
  area: string;
  preferred_time: string;
  session_id: string | null;
  timeline: TimelineStep[];
  /** Once a mechanic took the job: their first name only (never a phone number). */
  mechanic_first_name?: string | null;
  /** Status changes, newest first. */
  updates?: { at: string; status: string; label: string }[];
}

export interface AuthConfig {
  consent_version: string;
  consent_text: string;
  code_length: number;
  expires_in: number;
}

export const accountApi = {
  config: (signal?: AbortSignal) => get<AuthConfig>("/auth/config", signal),
  requestCode: (phone: string) =>
    post<{ sent: boolean; phone_masked: string; expires_in: number }>("/auth/otp/request", { phone }),
  verifyCode: (phone: string, code: string, consentVersion: string) =>
    post<{ user: User; attached: { sessions: number; requests: number } }>("/auth/otp/verify", {
      phone,
      code,
      consent: true,
      consent_text_version: consentVersion,
    }),
  logout: () => post<void>("/auth/logout"),
  me: (signal?: AbortSignal) => get<Me>("/me", signal),
  cars: (signal?: AbortSignal) => get<SavedCar[]>("/me/vehicles", signal),
  removeCar: (id: number) => del<void>(`/me/vehicles/${id}`),
  sessions: (signal?: AbortSignal) => get<SessionSummary[]>("/me/sessions", signal),
  requests: (signal?: AbortSignal) => get<RequestSummary[]>("/me/requests", signal),
  request: (id: string, signal?: AbortSignal) => get<RequestDetail>(`/requests/${encodeURIComponent(id)}`, signal),
  deleteAccount: () =>
    del<{ deleted: boolean; sessions: number; requests: number; vehicles: number }>("/me", { confirm: "DELETE" }),
};

// ---------------------------------------------------------------- Photos (backend/app/uploads)

export const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
export const PHOTO_MAX_BYTES = 10 * 1024 * 1024;

export interface UploadForm {
  upload_id: string;
  url: string;
  fields: Record<string, string>;
  max_bytes: number;
  expires_in: number;
}

export type PhotoMode = "warning_light" | "damage";

export interface FindingLabel {
  code: string;
  name: string;
  meaning: string;
  severity: "red" | "amber" | "info" | null;
  confidence: number;
  reviewed: boolean;
}

/** What a photo may show (backend/app/vision). Labels are possibilities, never verified facts. */
export interface Finding {
  upload_id: string;
  mode: PhotoMode;
  status: "found" | "unclear" | "unavailable" | "failed";
  message: string;
  labels: FindingLabel[];
  safety: SafetyAlert[];
}

export interface Photo {
  id: string;
  status: "pending" | "ready" | "rejected";
  width: number | null;
  height: number | null;
  url: string | null;
  expires_in: number | null;
  findings?: Finding[];
}

/** The type to declare for a file: browsers often leave HEIC photos untyped, so the extension decides then. */
export function photoType(file: File): string | null {
  const t = file.type.toLowerCase();
  if (PHOTO_TYPES.includes(t)) return t;
  if (!t && /\.(heic|heif)$/i.test(file.name)) return "image/heic";
  return null;
}

/** Send a file to the storage with a presigned POST form, reporting progress (0-1). */
export function sendToStorage(form: UploadForm, file: File, onProgress: (p: number) => void, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const body = new FormData();
    for (const [k, v] of Object.entries(form.fields)) body.append(k, v);
    body.append("file", file);
    xhr.open("POST", form.url);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new ApiError("The photo didn't upload. Please try again.", xhr.status));
    xhr.onerror = () => reject(new ApiError("The photo didn't upload. Check your connection and try again."));
    xhr.onabort = () => reject(new DOMException("aborted", "AbortError"));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(body);
  });
}

export const photosApi = {
  start: (sessionId: string, contentType: string, size: number) =>
    post<UploadForm>("/uploads", { session_id: sessionId, content_type: contentType, size }),
  complete: (id: string) => post<Photo>(`/uploads/${id}/complete`),
  list: (sessionId: string, signal?: AbortSignal) =>
    get<Photo[]>(`/uploads?session_id=${encodeURIComponent(sessionId)}`, signal),
  remove: (id: string) => del<void>(`/uploads/${id}`),
  analyze: (id: string, mode: PhotoMode) => post<Finding>(`/uploads/${id}/analyze`, { mode }),
};

// ---------------------------------------------------------------- Notifications (backend/app/notify)

export interface NotificationsConfig {
  push_public_key: string | null; // null: browser alerts are not set up on the server
  whatsapp_consent_version: string;
  whatsapp_consent_text: string;
}

export interface PushSubscriptionIn {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

export interface NotificationChoices {
  sms: boolean;
  push: boolean;
  whatsapp: { opted_in: boolean; since: string | null; consent_text_version: string; consent_text: string };
}

export const notifyApi = {
  config: (signal?: AbortSignal) => get<NotificationsConfig>("/notifications/config", signal),
  subscribe: (sub: PushSubscriptionIn) => post<{ ok: boolean }>("/notifications/push-subscriptions", sub),
  unsubscribe: (endpoint: string) => del<{ ok: boolean }>("/notifications/push-subscriptions", { endpoint }),
  choices: (signal?: AbortSignal) => get<NotificationChoices>("/me/notifications", signal),
  setChoices: (body: { sms?: boolean; push?: boolean }) => put<NotificationChoices>("/me/notifications", body),
  setWhatsapp: (optIn: boolean, version?: string) =>
    put<NotificationChoices>("/me/notifications/whatsapp", { opt_in: optIn, consent_text_version: version ?? null }),
};

// ---------------------------------------------------------------- Live tracking (backend/app/requests/tracking_api.py)

export interface Tracking {
  id: string;
  reference: string;
  status: string;
  status_label: string;
  timeline: TimelineStep[];
  mechanic: { first_name: string; photo_url: string | null } | null;
  eta_at: string | null;
  eta_minutes: number | null;
  can_call: boolean;
  poll_seconds: number;
  updated_at: string;
}

export const trackingApi = {
  get: (id: string, signal?: AbortSignal) => get<Tracking>(`/requests/${encodeURIComponent(id)}/tracking`, signal),
  call: (id: string) => post<{ status: string; message: string }>(`/requests/${encodeURIComponent(id)}/call`),
};
