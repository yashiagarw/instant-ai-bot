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

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api${path}`, { ...init, headers: { Accept: "application/json", ...init.headers } });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("We couldn't reach our server. Check your internet connection and try again.");
  }
  if (res.status === 429) throw new ApiError("Too many requests. Please wait a moment and try again.", 429);
  if (res.status === 404) throw new ApiError("We couldn't find that. Please go back and pick again.", 404);
  if (res.status === 409) throw new ApiError("This step has already moved on. Please refresh the page.", 409);
  if (res.status === 422) {
    // Plain-sentence reasons from the API (for example "enter a 6-digit pincode") are shown as they are.
    const detail = await res
      .json()
      .then((b: { detail?: unknown }) => b.detail)
      .catch(() => null);
    const message =
      typeof detail === "string"
        ? detail.charAt(0).toUpperCase() + detail.slice(1)
        : "Something in your answer didn't look right. Please check and try again.";
    throw new ApiError(message, 422);
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
  source: "answer" | "text" | "likely";
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
}

export interface ServiceRequestOut {
  reference: string;
  status: string;
  urgent: boolean;
  created_at: string;
  helpline_number: string;
  next_steps: string[];
}
