// A fake /api/admin for the admin app's Playwright tests (page.route on the API URL). It mirrors the real API's
// shapes and rules that the UI depends on: two-step login (password, then code), the two-factor setup step for
// accounts without it, permissions per role, and masked customer phones. Codes: 123456 signs in, 654321 finishes
// a setup; anything else is wrong.

import type { Page, Route } from "@playwright/test";

import { FakeDatasets } from "./fake-datasets";
import { FakeKnowledge } from "./fake-knowledge";
import { CATEGORIES, FakeOps } from "./fake-ops";
import { FakeParts } from "./fake-parts";

export const API = "http://localhost:8000/api/admin";
export const PASSWORD = "a long staff passphrase 1";
export const SETUP_KEY = "JBSWY3DPEHPK3PXPJBSWY3DP";

const PERMS: Record<string, string[]> = {
  super_admin: ["self", "staff.read", "staff.manage", "audit.read", "requests.read", "requests.contact",
    "requests.update", "customers.read", "customers.contact", "content.read", "content.review", "datasets.manage",
    "datasets.override", "knowledge.edit", "vehicles.manage", "mechanics.read", "mechanics.manage", "mechanics.documents"],
  content_admin: ["self", "content.read", "content.review", "datasets.manage", "knowledge.edit", "vehicles.manage"],
  support_agent: ["self", "requests.read", "requests.contact", "requests.update", "customers.read", "customers.contact",
    "mechanics.read", "mechanics.manage"],
  mechanic: ["self", "requests.read"],
}; // prettier-ignore

interface Account {
  id: string;
  email: string;
  name: string;
  roles: string[];
  active: boolean;
  locked: boolean;
  two_factor: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login_at: string | null;
  password: string;
}

let n = 0;
function account(email: string, roles: string[], over: Partial<Account> = {}): Account {
  return {
    id: `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`,
    email,
    name: email.split("@")[0].replace(/^\w/, (c) => c.toUpperCase()),
    roles,
    active: true,
    locked: false,
    two_factor: true,
    must_change_password: false,
    created_at: "2026-10-30T10:00:00Z",
    last_login_at: "2026-10-31T05:00:00Z",
    password: PASSWORD,
    ...over,
  };
}

export class FakeAdmin {
  accounts: Account[] = [
    account("boss@im.test", ["super_admin"]),
    account("content@im.test", ["content_admin"]),
    account("agent@im.test", ["support_agent"]),
    account("mech@im.test", ["mechanic"]),
    account("new@im.test", ["mechanic"], { two_factor: false, must_change_password: true, last_login_at: null }),
  ];
  customers = [
    { id: "c1", name: "Ravi Kumar", phone: "+919811112222", phone_masked: "******2222", created_at: "2026-10-01T09:00:00Z",
      last_login_at: "2026-10-31T09:00:00Z", diagnoses: 3, requests: 1 },
    { id: "c2", name: "Asha", phone: "+919800003333", phone_masked: "******3333", created_at: "2026-10-05T09:00:00Z",
      last_login_at: null, diagnoses: 1, requests: 0 },
  ]; // prettier-ignore
  audit = [
    { id: 2, at: "2026-10-31T06:00:00Z", actor_id: null, actor_label: "boss@im.test", action: "staff.set_roles",
      entity_type: "staff_user", entity_id: "x", before: { roles: ["mechanic"] }, after: { roles: ["support_agent"] }, ip: "127.0.0.1" },
    { id: 1, at: "2026-10-30T06:00:00Z", actor_id: null, actor_label: "cli", action: "staff.create",
      entity_type: "staff_user", entity_id: "y", before: null, after: { email: "boss@im.test" }, ip: null },
  ]; // prettier-ignore
  signedIn: Account | null = null;
  pending: Account | null = null; // between password and setup confirm
  auditQueries: string[] = [];
  datasets = new FakeDatasets();
  parts = new FakeParts();
  knowledge = new FakeKnowledge(this.parts);
  ops = new FakeOps();
  revealed: string[] = [];

  /** Signed in already (skips the login screen). */
  as(email: string): this {
    this.signedIn = this.find(email)!;
    return this;
  }

  private find(email: string) {
    return this.accounts.find((a) => a.email === email.trim().toLowerCase());
  }

  private out(a: Account) {
    const { password: _p, ...rest } = a;
    void _p;
    return rest;
  }

  private me(a: Account) {
    const perms = [...new Set(a.roles.flatMap((r) => PERMS[r]))].sort();
    return { ...this.out(a), permissions: perms, session_expires_at: "2026-11-01T18:00:00Z" };
  }

  handle(method: string, path: string, url: URL, body: Record<string, unknown>, raw: string | null = null): { status: number; json?: unknown } {
    if (path === "/auth/login" && method === "POST") {
      const a = this.find(String(body.email));
      if (!a || a.password !== body.password) return { status: 401, json: { detail: "Email, password or code is wrong." } };
      if (!a.two_factor) {
        this.pending = a;
        return { status: 200, json: { next: "setup", me: null, setup: {
          otpauth_uri: `otpauth://totp/Instant%20Mechanic:${a.email}?secret=${SETUP_KEY}`, secret: SETUP_KEY,
          qr_svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>' } } }; // prettier-ignore
      }
      if (!body.code) return { status: 200, json: { next: "code", me: null, setup: null } };
      if (body.code !== "123456") return { status: 401, json: { detail: "Email, password or code is wrong." } };
      this.signedIn = a;
      return { status: 200, json: { next: "done", me: this.me(a), setup: null } };
    }
    if (path === "/auth/two-factor/confirm" && method === "POST") {
      if (!this.pending) return { status: 401, json: { detail: "This setup has expired. Please sign in again." } };
      if (body.code !== "654321") {
        return { status: 401, json: { detail: "That code doesn't match. Make sure the phone's time is set automatically and type the newest code." } };
      }
      this.pending.two_factor = true;
      this.signedIn = this.pending;
      this.pending = null;
      return { status: 200, json: this.me(this.signedIn) };
    }
    const a = this.signedIn;
    if (!a) return { status: 401, json: { detail: "Please sign in as staff" } };
    const perms = new Set(a.roles.flatMap((r) => PERMS[r]));
    const need = (p: string) => (perms.has(p) ? null : { status: 403, json: { detail: "You don't have access to this" } });

    if (path === "/auth/me") return { status: 200, json: this.me(a) };
    if (path === "/auth/logout") {
      this.signedIn = null;
      return { status: 204 };
    }
    if (path === "/auth/password") {
      if (body.current_password !== a.password || body.code !== "123456") {
        return { status: 422, json: { detail: "Current password or code is wrong" } };
      }
      a.password = String(body.new_password);
      a.must_change_password = false;
      return { status: 204 };
    }
    if (a.must_change_password) return { status: 403, json: { detail: "Choose your own password first" } };

    if (path === "/staff" && method === "GET") return need("staff.read") ?? { status: 200, json: this.accounts.map((x) => this.out(x)) };
    if (path === "/staff" && method === "POST") {
      const denied = need("staff.manage");
      if (denied) return denied;
      const created = account(String(body.email), body.roles as string[], {
        name: String(body.name), two_factor: false, must_change_password: true, last_login_at: null,
      }); // prettier-ignore
      this.accounts.push(created);
      return { status: 201, json: { staff: this.out(created), temporary_password: "Tmp-9xQ2-wE7r-Lk4z" } };
    }
    const staffAction = path.match(/^\/staff\/([^/]+)\/(roles|deactivate|activate|unlock|reset-two-factor)$/);
    if (staffAction) {
      const denied = need("staff.manage");
      if (denied) return denied;
      const t = this.accounts.find((x) => x.id === staffAction[1])!;
      if (staffAction[2] === "roles") t.roles = body.roles as string[];
      if (staffAction[2] === "deactivate") t.active = false;
      if (staffAction[2] === "activate") t.active = true;
      if (staffAction[2] === "unlock") t.locked = false;
      if (staffAction[2] === "reset-two-factor") t.two_factor = false;
      return { status: 200, json: this.out(t) };
    }
    if (path === "/customers") {
      return need("customers.read") ?? { status: 200, json: this.customers.map(({ phone: _p, ...c }) => (void _p, c)) };
    }
    const reveal = path.match(/^\/customers\/([^/]+)\/reveal-phone$/);
    if (reveal) {
      const denied = need("customers.contact");
      if (denied) return denied;
      this.revealed.push(reveal[1]);
      return { status: 200, json: { phone: this.customers.find((c) => c.id === reveal[1])!.phone } };
    }
    if (path === "/audit") {
      const denied = need("audit.read");
      if (denied) return denied;
      this.auditQueries.push(url.search);
      const action = url.searchParams.get("action");
      return { status: 200, json: this.audit.filter((r) => !action || r.action === action) };
    }
    return (
      this.datasets.handle(method, path, url, body, perms, a.email) ??
      this.ops.handle(method, path, url, body, perms, a.email, a.name) ??
      this.parts.handle(method, path, body, perms, a.email, raw, url) ??
      this.knowledge.handle(method, path, body, perms) ?? { status: 404, json: { detail: "Not Found" } }
    );
  }

  async install(page: Page): Promise<this> {
    // The public category list (names for skills and filters) and no map tiles from the internet in tests.
    await page.route("http://localhost:8000/api/categories", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ categories: CATEGORIES, topics: [] }) }),
    );
    await page.route(/tile\.openstreetmap\.org/, (route) => route.abort());
    await page.route(`${API}/**`, async (route: Route) => {
      const req = route.request();
      const url = new URL(req.url());
      const path = url.pathname.replace("/api/admin", "");
      const raw = req.headers()["content-type"]?.includes("json") ? req.postData() : null; // uploads are files
      const res = this.handle(req.method(), path, url, raw ? JSON.parse(raw) : {}, raw ? null : req.postData());
      await route.fulfill({
        status: res.status,
        contentType: "application/json",
        body: res.json === undefined ? "" : JSON.stringify(res.json),
      });
    });
    return this;
  }
}
