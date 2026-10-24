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
  mode: "diagnose" | "fast_track" | "inspect";
  categories: string[];
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
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api${path}`, { signal, headers: { Accept: "application/json" } });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("We couldn't reach our server. Check your internet connection and try again.");
  }
  if (res.status === 429) throw new ApiError("Too many requests. Please wait a moment and try again.", 429);
  if (res.status === 404) throw new ApiError("We couldn't find that. Please go back and pick again.", 404);
  if (!res.ok) throw new ApiError("Something went wrong on our side. Please try again.", res.status);
  return (await res.json()) as T;
}

export const api = {
  categories: (signal?: AbortSignal) => get<CategoriesResult>("/categories", signal),
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
