// A fake mechanic app API (backend/app/mechanics/app_api.py) and customer tracking (tracking_api.py), with the same
// rules: only the signed-in mechanic's offers, no address before accepting, steps in order, the fault at the end.
import { FakeDiagnosis, type FakeResponse } from "./fake-diagnosis";

const NOW = () => new Date().toISOString();
export const CODE = "246810";
export const REQUEST_ID = "7c1f0d8e-0000-4000-8000-000000000001";

type Status = "offered" | "accepted" | "en_route" | "arrived" | "in_progress" | "completed" | "declined" | "expired";
const NEXT: Record<string, string> = { accepted: "en_route", en_route: "arrived", arrived: "in_progress", in_progress: "completed" };
const LABELS: Record<string, string> = {
  submitted: "Request received",
  offered: "Finding a mechanic for you",
  accepted: "Mechanic assigned",
  en_route: "Mechanic on the way",
  arrived: "Mechanic has arrived",
  in_progress: "Repair in progress",
  completed: "Done",
};

export class FakeMechanic extends FakeDiagnosis {
  signedIn = false;
  onDuty = true;
  offerStatus: Status = "offered";
  requestStatus = "offered";
  secondsLeft = 175;
  etaMinutes: number | null = null;
  calls: string[] = [];
  outcome: Record<string, unknown> | null = null;
  pushSubscriptions: Record<string, unknown>[] = [];
  search = ""; // the query string of the current call (set by the API mocks)

  private me() {
    return {
      id: 7,
      name: "Ravi Kumar",
      first_name: "Ravi",
      phone_masked: "+91******0011",
      on_duty: this.onDuty,
      photo_url: null,
      jobs_today: this.offerStatus === "accepted" || this.offerStatus === "completed" ? 1 : 0,
      open_offers: this.offerStatus === "offered" ? 1 : 0,
    };
  }

  offer() {
    return {
      id: 41,
      reference: "IM-7K3Q9P",
      job_type: "at_location",
      job_type_label: "At the car's location",
      car: "Maruti Suzuki Swift petrol",
      problem: "Battery, lights & warning lights · likely cause: Weak battery (high confidence)",
      area: "Delhi, pincode 110017",
      distance_km: 4,
      urgent: false,
      safety_critical: false,
      offered_at: NOW(),
      expires_at: new Date(Date.now() + this.secondsLeft * 1000).toISOString(),
      seconds_left: this.secondsLeft,
    };
  }

  job() {
    const status = this.requestStatus;
    return {
      id: 41,
      request_id: REQUEST_ID,
      reference: "IM-7K3Q9P",
      status,
      job_type: "at_location",
      job_type_label: "At the car's location",
      car: "Maruti Suzuki Swift petrol",
      problem: "Battery, lights & warning lights · likely cause: Weak battery (high confidence)",
      area: "Delhi, pincode 110017",
      address: "B-12, 2nd floor, Malviya Nagar, 110017",
      map_url: "https://www.google.com/maps/search/?api=1&query=B-12%2C%202nd%20floor",
      customer_name: "Asha",
      customer_phone: "+91******1234",
      notes: "Car is in the basement parking",
      urgent: false,
      safety_critical: false,
      eta_at: this.etaMinutes ? new Date(Date.now() + this.etaMinutes * 60000).toISOString() : null,
      can_call: ["accepted", "en_route", "arrived", "in_progress"].includes(status),
      next_status: this.offerStatus === "accepted" ? (NEXT[status] ?? null) : null,
      accepted_at: NOW(),
    };
  }

  handle(method: string, path: string, body?: unknown): FakeResponse | null {
    const b = (body ?? {}) as Record<string, unknown>;
    if (path === `/api/requests/${REQUEST_ID}/tracking`) return { status: 200, json: this.tracking() };
    if (path === `/api/requests/${REQUEST_ID}/call` && method === "POST") {
      this.calls.push("customer_to_mechanic");
      return { status: 200, json: { status: "ringing", message: "We are calling your phone now. Pick up to be connected." } };
    }
    if (!path.startsWith("/api/mechanic/")) return super.handle(method, path, body);
    const p = path.slice("/api/mechanic".length);
    if (p === "/auth/otp/request") return { status: 202, json: { sent: true, phone_masked: "+91******0011" } };
    if (p === "/auth/otp/verify") {
      if (b.code !== CODE) return { status: 400, json: { detail: "That code is not right. 4 tries left." } };
      this.signedIn = true;
      return { status: 200, json: { ok: true, first_name: "Ravi" } };
    }
    if (!this.signedIn) return { status: 401, json: { detail: "Please sign in" } };
    if (p === "/auth/logout") {
      this.signedIn = false;
      return { status: 200, json: { ok: true } };
    }
    if (p === "/me") return { status: 200, json: this.me() };
    if (p === "/availability") {
      this.onDuty = Boolean(b.on_duty);
      return { status: 200, json: this.me() };
    }
    if (p === "/offers") return { status: 200, json: this.offerStatus === "offered" ? [this.offer()] : [] };
    if (p === "/offers/41/accept" || p === "/offers/41/reject") {
      if (this.offerStatus !== "offered") return { status: 409, json: { detail: `This offer can't be answered: the offer is ${this.offerStatus}.` } };
      const accept = p.endsWith("accept");
      this.offerStatus = accept ? "accepted" : "declined";
      this.requestStatus = accept ? "accepted" : "triaged";
      return { status: 200, json: accept ? this.job() : { ok: true } };
    }
    const accepted = this.offerStatus === "accepted" || this.offerStatus === "completed";
    if (p === "/jobs") return { status: 200, json: accepted ? [this.job()] : [] };
    if (!p.startsWith("/jobs/41") || !accepted) return { status: 404, json: { detail: "Not found" } };
    if (p === "/jobs/41") return { status: 200, json: this.job() };
    if (p === "/jobs/41/eta") {
      this.etaMinutes = Number(b.minutes);
      return { status: 200, json: this.job() };
    }
    if (p.startsWith("/jobs/41/faults")) {
      const q = new URLSearchParams(this.search).get("q") ?? "";
      const all = [
        { fault_key: "F08-BT-01", name: "Weak battery", name_hi: "बैटरी कमज़ोर है", category: "Battery", ai_rank: 1 },
        { fault_key: "F08-BT-04", name: "Loose battery terminal", name_hi: "battery ka terminal dheela", category: "Battery", ai_rank: null },
      ];
      return { status: 200, json: all.filter((f) => !q || `${f.name} ${f.name_hi}`.toLowerCase().includes(q.toLowerCase())) };
    }
    if (p === "/jobs/41/call") {
      this.calls.push("mechanic_to_customer");
      return { status: 200, json: { status: "ringing", message: "We are calling your phone now." } };
    }
    if (p === "/jobs/41/status") {
      if (NEXT[this.requestStatus] !== b.status) return { status: 409, json: { detail: `This job is ${this.requestStatus}: it can't become ${String(b.status)} now.` } };
      if (b.status === "completed") {
        if (!b.confirmed_fault_key) return { status: 422, json: { detail: 'Pick the fault you found, or "other".' } };
        if (b.confirmed_fault_key === "other" && !String(b.other_text ?? "").trim()) {
          return { status: 422, json: { detail: 'Say what the fault was when it is "other".' } };
        }
        this.outcome = b;
        this.offerStatus = "completed";
      }
      this.requestStatus = String(b.status);
      if (b.eta_minutes) this.etaMinutes = Number(b.eta_minutes);
      return { status: 200, json: this.job() };
    }
    if (p === "/push-subscriptions") {
      this.pushSubscriptions.push(b);
      return { status: 201, json: { ok: true } };
    }
    return { status: 404, json: { detail: "Not found" } };
  }

  tracking() {
    const s = this.requestStatus === "triaged" ? "offered" : this.requestStatus;
    const order = ["submitted", "triaged", "accepted", "en_route", "arrived", "in_progress", "completed"];
    const at = order.indexOf(s === "offered" ? "triaged" : s);
    const onJob = ["accepted", "en_route", "arrived", "in_progress"].includes(s);
    return {
      id: REQUEST_ID,
      reference: "IM-7K3Q9P",
      status: s,
      status_label: LABELS[s],
      timeline: order.map((k, i) => ({
        key: k,
        label: k,
        state: i < at || (i === at && k === "completed") ? "done" : i === at ? "current" : "upcoming",
        at: i <= at ? NOW() : null,
      })),
      mechanic: onJob || s === "completed" ? { first_name: "Ravi", photo_url: null } : null,
      eta_at: null,
      eta_minutes: ["accepted", "en_route"].includes(s) ? this.etaMinutes : null,
      can_call: onJob,
      poll_seconds: 1,
      updated_at: NOW(),
    };
  }
}
