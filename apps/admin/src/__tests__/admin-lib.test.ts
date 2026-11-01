import { afterEach, expect, test, vi } from "vitest";

import { dayBoundary } from "@/components/audit-view";
import { groupKey, safeNext } from "@/components/login-view";
import { adminApi, ApiError } from "@/lib/api";
import { staffStatus } from "@/lib/format";
import { NAV, visibleNav } from "@/lib/nav";

afterEach(() => vi.unstubAllGlobals());

test("after sign-in only paths on this site are followed (no open redirect)", () => {
  expect(safeNext("?next=%2Fusers")).toBe("/users");
  expect(safeNext("?next=https://evil.test")).toBe("/");
  expect(safeNext("?next=//evil.test")).toBe("/");
  expect(safeNext("?next=/%5Cevil.test")).toBe("/");
  expect(safeNext("")).toBe("/");
});

test("menu items follow permissions; every page has one item", () => {
  const labels = (perms: string[]) => visibleNav(perms).map((i) => i.label);
  expect(labels(["self"])).toEqual(["Overview"]);
  expect(labels(["self", "requests.read"])).toEqual(["Overview", "Requests"]);
  expect(labels(["self", "requests.read", "mechanics.read"])).toEqual(["Overview", "Requests", "Mechanics"]);
  expect(labels(["self", "customers.read"])).toEqual(["Overview", "Users"]);
  expect(labels([])).toEqual([]);
  expect(NAV).toHaveLength(10);
  expect(new Set(NAV.map((i) => i.href)).size).toBe(10);
});

test("setup key in groups of four; staff status worst first; IST day boundaries", () => {
  expect(groupKey("JBSWY3DPEHPK3PXP")).toBe("JBSW Y3DP EHPK 3PXP");
  const ok = { active: true, locked: false, two_factor: true, must_change_password: false };
  expect(staffStatus(ok)).toBe("Active");
  expect(staffStatus({ ...ok, two_factor: false, must_change_password: true })).toBe("Two-factor not set up");
  expect(staffStatus({ ...ok, active: false, locked: true })).toBe("Disabled");
  expect(dayBoundary("2026-11-01", false)).toBe("2026-10-31T18:30:00.000Z");
  expect(dayBoundary("2026-11-01", true)).toBe("2026-11-01T18:29:59.999Z");
  expect(dayBoundary("", true)).toBeUndefined();
});

test("API errors keep the server's sentence; calls send the staff cookie", async () => {
  const fetchMock = vi.fn<typeof fetch>(
    async () => new Response(JSON.stringify({ detail: "You don't have access to this" }), { status: 403 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const err = await adminApi.staff().catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect([err.status, err.message]).toEqual([403, "You don't have access to this"]);
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include", cache: "no-store" });
  vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
  expect((await adminApi.me().catch((e) => e)).message).toMatch(/couldn't reach the server/);
});
