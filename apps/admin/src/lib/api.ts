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
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/admin${path}`, {
      method,
      credentials: "include",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
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
};
