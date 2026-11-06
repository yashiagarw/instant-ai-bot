// Client for the mechanic app API (backend/app/mechanics/app_api.py). The mechanic's sign-in cookie (im_mech,
// HttpOnly, path /api/mechanic) goes with every call. Errors carry the status: 401 = sign in again.

import { newRequestId } from "@im/ui/observability";

import { API_URL, humanHeader } from "@/lib/api";

export class MechanicApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "MechanicApiError";
  }
}

async function call<T>(method: string, path: string, body?: unknown, signal?: AbortSignal, extra?: Record<string, string>): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/mechanic${path}`, {
      method,
      signal,
      credentials: "include",
      headers: {
        Accept: "application/json",
        "X-Request-ID": newRequestId("mech"),
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...extra,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new MechanicApiError("offline", 0);
  }
  if (res.ok) return (await res.json()) as T;
  const detail = await res
    .json()
    .then((b: { detail?: unknown }) => (typeof b.detail === "string" ? b.detail : ""))
    .catch(() => "");
  throw new MechanicApiError(detail, res.status);
}

export interface MechanicMe {
  id: number;
  name: string;
  first_name: string;
  phone_masked: string;
  on_duty: boolean;
  photo_url: string | null;
  jobs_today: number;
  open_offers: number;
}

export interface Offer {
  id: number;
  reference: string;
  job_type: "at_location" | "tow" | "workshop";
  job_type_label: string;
  car: string;
  problem: string;
  area: string;
  distance_km: number | null;
  urgent: boolean;
  safety_critical: boolean;
  offered_at: string;
  expires_at: string | null;
  seconds_left: number | null;
}

export type JobStatus = "accepted" | "en_route" | "arrived" | "in_progress" | "completed";

export interface Job {
  id: number;
  request_id: string;
  reference: string;
  status: JobStatus | string;
  job_type: Offer["job_type"];
  job_type_label: string;
  car: string;
  problem: string;
  area: string;
  address: string;
  map_url: string;
  customer_name: string;
  customer_phone: string;
  notes: string;
  urgent: boolean;
  safety_critical: boolean;
  eta_at: string | null;
  can_call: boolean;
  next_status: JobStatus | null;
  accepted_at: string | null;
}

export interface FaultChoice {
  fault_key: string;
  name: string;
  name_hi: string | null;
  category: string;
  ai_rank: number | null;
}

export interface StatusIn {
  status: Exclude<JobStatus, "accepted">;
  eta_minutes?: number;
  confirmed_fault_key?: string;
  other_text?: string;
  notes?: string;
}

export const mechanicApi = {
  requestCode: (phone: string, human?: string) =>
    call<{ sent: boolean; phone_masked: string }>("POST", "/auth/otp/request", { phone }, undefined, humanHeader(human)),
  verifyCode: (phone: string, code: string) => call<{ ok: boolean; first_name: string }>("POST", "/auth/otp/verify", { phone, code }),
  logout: () => call<{ ok: boolean }>("POST", "/auth/logout"),
  me: (signal?: AbortSignal) => call<MechanicMe>("GET", "/me", undefined, signal),
  setOnDuty: (on: boolean) => call<MechanicMe>("PUT", "/availability", { on_duty: on }),
  offers: (signal?: AbortSignal) => call<Offer[]>("GET", "/offers", undefined, signal),
  accept: (id: number) => call<Job>("POST", `/offers/${id}/accept`),
  reject: (id: number) => call<{ ok: boolean }>("POST", `/offers/${id}/reject`),
  jobs: (signal?: AbortSignal) => call<Job[]>("GET", "/jobs", undefined, signal),
  job: (id: number, signal?: AbortSignal) => call<Job>("GET", `/jobs/${id}`, undefined, signal),
  setStatus: (id: number, body: StatusIn) => call<Job>("POST", `/jobs/${id}/status`, body),
  setEta: (id: number, minutes: number) => call<Job>("POST", `/jobs/${id}/eta`, { minutes }),
  faults: (id: number, q: string, signal?: AbortSignal) =>
    call<FaultChoice[]>("GET", `/jobs/${id}/faults?q=${encodeURIComponent(q)}`, undefined, signal),
  callCustomer: (id: number) => call<{ status: string; message: string }>("POST", `/jobs/${id}/call`),
  subscribe: (sub: { endpoint: string; keys: { p256dh: string; auth: string } }) =>
    call<{ ok: boolean }>("POST", "/push-subscriptions", sub),
};
