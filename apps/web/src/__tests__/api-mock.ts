import { vi } from "vitest";

import { categoriesFor, CATEGORIES, MAKES, MODELS, SEARCH, VARIANTS } from "./api-data";
import { FakeDiagnosis } from "./fake-diagnosis";

export { CATEGORIES, MAKES, MODELS, SEARCH, VARIANTS };

export type Routes = Record<string, unknown | ((url: URL) => unknown)>;

/** Replace fetch: the first route whose path prefix matches answers with JSON; "fail" answers 500,
 * "offline" rejects like a network error. */
export function mockApi(overrides: Routes = {}, diagnosis = new FakeDiagnosis()) {
  const routes: Routes = {
    "/api/categories": categoriesFor,
    "/api/vehicles/makes/1/models": MODELS,
    "/api/vehicles/makes": MAKES,
    "/api/vehicles/models/5/variants": VARIANTS,
    "/api/vehicles/search": SEARCH,
    ...overrides,
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    // Next internals may fetch non-API resources in jsdom (e.g. `undefined`): answer them with 404.
    if (!URL.canParse(String(input))) return new Response("not found", { status: 404 });
    const url = new URL(String(input));
    const overridden = Object.keys(overrides).some((k) => url.pathname.startsWith(k));
    const fake = overridden
      ? null
      : diagnosis.handle(init?.method ?? "GET", url.pathname, init?.body ? JSON.parse(String(init.body)) : undefined);
    if (fake?.text !== undefined) {
      return new Response(fake.text, { status: fake.status, headers: { "Content-Type": fake.contentType ?? "text/plain" } });
    }
    if (fake) return new Response(JSON.stringify(fake.json), { status: fake.status, headers: { "Content-Type": "application/json" } });
    const key = Object.keys(routes).find((k) => url.pathname.startsWith(k));
    if (!key) return new Response("not found", { status: 404 });
    const value = routes[key];
    const body = typeof value === "function" ? (value as (u: URL) => unknown)(url) : value;
    if (body === "offline") throw new TypeError("Failed to fetch");
    if (body === "fail") return new Response("error", { status: 500 });
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
