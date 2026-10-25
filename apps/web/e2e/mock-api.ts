import type { Page } from "@playwright/test";

import { categoriesFor, MAKES, MODELS, SEARCH, VARIANTS } from "../src/__tests__/api-data";
import { FakeDiagnosis } from "../src/__tests__/fake-diagnosis";

const ROUTES: [string, (url: URL) => unknown][] = [
  ["/api/categories", categoriesFor],
  ["/api/vehicles/makes/1/models", () => MODELS],
  ["/api/vehicles/makes", () => MAKES],
  ["/api/vehicles/models/5/variants", () => VARIANTS],
  ["/api/vehicles/search", () => SEARCH],
];

const PICTURE = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 30"><rect width="40" height="30" fill="#ffe6d3"/></svg>`;

/** Answer the browser's API calls (http://localhost:8000) without a backend. Returns the fake diagnosis store. */
export async function mockApi(page: Page): Promise<FakeDiagnosis> {
  const fake = new FakeDiagnosis();
  await page.route("http://localhost:8000/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (url.pathname.startsWith("/media/")) return route.fulfill({ contentType: "image/svg+xml", body: PICTURE });
    const answer = fake.handle(req.method(), url.pathname, req.postData() ? JSON.parse(req.postData()!) : undefined);
    if (answer?.text !== undefined) return route.fulfill({ status: answer.status, body: answer.text, contentType: answer.contentType });
    if (answer) return route.fulfill({ status: answer.status, json: answer.json });
    const hit = ROUTES.find(([prefix]) => url.pathname.startsWith(prefix));
    if (!hit) return route.fulfill({ status: 404, body: "not found" });
    await route.fulfill({ json: hit[1](url) });
  });
  return fake;
}
