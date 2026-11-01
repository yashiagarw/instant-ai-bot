// A fake accounts API on top of the fake diagnosis (unit tests and Playwright): OTP login with the code 123456,
// /api/me, saved cars, history, requests with a status timeline, logout and account deletion.

import type { AuthConfig, Me, RequestDetail, SavedCar, SessionSummary } from "@/lib/api";
import { FakeDiagnosis, type FakeResponse } from "./fake-diagnosis";

export const CODE = "123456";

export const AUTH_CONFIG: AuthConfig = {
  consent_version: "account-v1",
  consent_text:
    "I agree that Instant Mechanic stores my mobile number to create my account and keep my cars, diagnoses and requests in it. I can delete my account and this data at any time.",
  code_length: 6,
  expires_in: 300,
};

const REQUEST: RequestDetail = {
  id: "7b0f2c1e-0000-4000-8000-000000000001",
  reference: "IM-7K3Q9P",
  created_at: "2026-10-30T09:15:00Z",
  status: "en_route",
  status_label: "Mechanic on the way",
  urgent: false,
  vehicle: "Maruti Suzuki Swift · Petrol 1.2 AMT",
  problem_summary: "Slow/pinhole puncture",
  service_type: "at_location",
  area: "Sector 62, Noida",
  preferred_time: "asap",
  session_id: "d6f3b8a2-0000-4000-8000-000000000002",
  timeline: [
    { key: "submitted", label: "Request received", state: "done", at: "2026-10-30T09:15:00Z" },
    { key: "triaged", label: "Our team is on it", state: "done", at: "2026-10-30T09:20:00Z" },
    { key: "accepted", label: "Mechanic assigned", state: "done", at: "2026-10-30T09:40:00Z" },
    { key: "en_route", label: "Mechanic on the way", state: "current", at: "2026-10-30T09:45:00Z" },
    { key: "arrived", label: "Mechanic has arrived", state: "upcoming", at: null },
    { key: "in_progress", label: "Repair in progress", state: "upcoming", at: null },
    { key: "completed", label: "Done", state: "upcoming", at: null },
  ],
  mechanic_first_name: "Sunita",
  updates: [
    { at: "2026-10-30T09:45:00Z", status: "en_route", label: "Mechanic on the way" },
    { at: "2026-10-30T09:40:00Z", status: "accepted", label: "Mechanic assigned" },
    { at: "2026-10-30T09:30:00Z", status: "offered", label: "Finding a mechanic for you" },
    { at: "2026-10-30T09:20:00Z", status: "triaged", label: "Our team is on it" },
    { at: "2026-10-30T09:15:00Z", status: "submitted", label: "Request received" },
  ],
};

export class FakeSite extends FakeDiagnosis {
  loggedIn = false;
  deleted = false;
  tries = 0;
  cars: SavedCar[] = [{ id: 1, label: "Maruti Suzuki Swift · Petrol 1.2 AMT", variant_id: 16, created_at: "2026-10-30T09:00:00Z" }];
  history: SessionSummary[] = [
    {
      session_id: "d6f3b8a2-0000-4000-8000-000000000002",
      created_at: "2026-10-30T09:00:00Z",
      status: "completed",
      vehicle: "Maruti Suzuki Swift · Petrol 1.2 AMT",
      topic: "Tyres",
      top_cause: "Slow/pinhole puncture",
    },
  ];

  handle(method: string, path: string, body?: unknown): FakeResponse | null {
    const b = (body ?? {}) as Record<string, unknown>;
    const unauthorised = { status: 401, json: { detail: "Please log in" } };
    if (path === "/api/auth/config") return { status: 200, json: AUTH_CONFIG };
    if (path === "/api/auth/otp/request" && method === "POST") {
      const phone = String(b.phone ?? "");
      if (!/^[6-9]\d{9}$/.test(phone)) return { status: 422, json: { detail: "Enter a 10-digit Indian mobile number" } };
      return { status: 202, json: { sent: true, phone_masked: `+91******${phone.slice(-4)}`, expires_in: 300 } };
    }
    if (path === "/api/auth/otp/verify" && method === "POST") {
      if (!b.consent) return { status: 422, json: { detail: "Please tick the box to agree before logging in" } };
      if (b.code !== CODE) {
        this.tries += 1;
        return { status: 400, json: { detail: `That code is not right. ${5 - this.tries} tries left.` } };
      }
      this.loggedIn = true;
      return { status: 200, json: { user: this.user(), attached: { sessions: 1, requests: 1 } } };
    }
    if (path === "/api/auth/logout") {
      this.loggedIn = false;
      return { status: 200, json: {} };
    }
    if (path.startsWith("/api/me") || path.startsWith("/api/requests/")) {
      if (!this.loggedIn) return unauthorised;
      if (path === "/api/me" && method === "GET") return { status: 200, json: this.me() };
      if (path === "/api/me" && method === "DELETE") {
        this.loggedIn = false;
        this.deleted = true;
        return { status: 200, json: { deleted: true, sessions: 1, requests: 1, vehicles: this.cars.length } };
      }
      if (path === "/api/me/vehicles") return { status: 200, json: this.cars };
      const car = path.match(/^\/api\/me\/vehicles\/(\d+)$/);
      if (car && method === "DELETE") {
        this.cars = this.cars.filter((c) => c.id !== Number(car[1]));
        return { status: 200, json: {} };
      }
      if (path === "/api/me/sessions") return { status: 200, json: this.history };
      if (path === "/api/me/requests") return { status: 200, json: [REQUEST] };
      if (path === `/api/requests/${REQUEST.id}`) return { status: 200, json: REQUEST };
      return { status: 404, json: { detail: "Request not found" } };
    }
    return super.handle(method, path, body);
  }

  private user() {
    return { id: "u-1", phone_masked: "+91******3210", name: null, created_at: "2026-10-30T09:00:00Z" };
  }

  private me(): Me {
    return { user: this.user(), vehicles: this.cars.length, sessions: this.history.length, requests: 1 };
  }
}

export { REQUEST };
