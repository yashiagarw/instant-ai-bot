import { expect, test } from "@playwright/test";

// Smoke test of a running production stack (docker-compose.prod.yml), through Caddy and real HTTPS. Opt-in:
//   cd apps/web && E2E_BASE_URL=https://localhost E2E_API_URL=https://api.localhost \
//     E2E_ADMIN_URL=https://admin.localhost E2E_FILES_URL=https://files.localhost \
//     pnpm exec playwright test e2e/prod-smoke.spec.ts --workers=1
// Needs the data imported (README "Phase 5.1"). It creates real diagnosis sessions and stores a 1-pixel photo.
const API = process.env.E2E_API_URL;
const ADMIN = process.env.E2E_ADMIN_URL;
const FILES = process.env.E2E_FILES_URL;
const BUCKET = process.env.E2E_BUCKET ?? "autocare-uploads";
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

test.skip(!process.env.E2E_BASE_URL || !API, "production smoke test: set E2E_BASE_URL and E2E_API_URL (see the top)");
test.setTimeout(90_000);

test("API is healthy behind the proxy, with HTTPS and no server banner", async ({ request }) => {
  const res = await request.get(`${API}/api/health`);
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual({ status: "ok", database: "ok" });
  expect(res.headers()["server"]).toBeUndefined();
  expect(res.headers()["x-content-type-options"]).toBe("nosniff");
});

test("API CORS allows the web origin only", async ({ request, baseURL }) => {
  const origin = new URL(baseURL!).origin;
  const allowed = await request.get(`${API}/api/categories`, { headers: { Origin: origin } });
  expect(allowed.ok()).toBe(true);
  expect(allowed.headers()["access-control-allow-origin"]).toBe(origin);
  const other = await request.get(`${API}/api/categories`, { headers: { Origin: "https://evil.example" } });
  expect(other.headers()["access-control-allow-origin"]).toBeUndefined();
});

test("customer site: home tiles come from the API, and a diagnosis starts", async ({ page }) => {
  const apiErrors: string[] = [];
  page.on("response", (r) => {
    if (r.url().startsWith(API!) && r.status() >= 500) apiErrors.push(`${r.status()} ${r.url()}`);
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.goto("/diagnose");
  await page.getByLabel("Search for your car").fill("alto k10 petrol");
  await page.getByRole("button", { name: /Maruti Suzuki Alto K10/ }).first().click();
  await page.getByRole("button", { name: /Battery, lights & warning lights/ }).click();
  await expect(page).toHaveURL(/\/diagnose\/[0-9a-f-]{36}$/, { timeout: 30_000 });
  const battery = page.getByRole("button", { name: "Battery", exact: true });
  if (await battery.isVisible().catch(() => false)) await battery.click();
  await expect(page.locator("#question-heading")).toBeVisible({ timeout: 30_000 });

  // A real photo: presigned POST from the browser to the storage (FILES host), processed by the API, then shown
  // through a signed link. Skipped when the deployment has no storage behind E2E_FILES_URL.
  if (FILES) {
    const step = page.getByTestId("photo-step");
    await step.getByTestId("gallery-input").setInputFiles({ name: "dash.png", mimeType: "image/png", buffer: PNG });
    await step.getByRole("button", { name: "Use this photo" }).click();
    await expect(step.getByTestId("photo-status")).toContainText("Photo added", { timeout: 30_000 });
    const photo = step.getByRole("img", { name: "Your photo 1" });
    await expect(photo).toBeVisible();
    expect(await photo.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  }
  expect(apiErrors).toEqual([]);
});

test("admin app serves its sign-in page with its security headers", async ({ request, page }) => {
  test.skip(!ADMIN, "set E2E_ADMIN_URL");
  const res = await request.get(`${ADMIN}/login`);
  expect(res.status()).toBe(200);
  expect(res.headers()["x-frame-options"]).toBe("DENY");
  expect(res.headers()["x-robots-tag"]).toContain("noindex");
  await page.goto(`${ADMIN}/login`);
  await expect(page.getByRole("heading", { name: "Staff sign in" })).toBeVisible();
});

test("photo storage lets the web origin post uploads and refuses other origins (CORS preflight)", async ({
  request,
  baseURL,
}) => {
  test.skip(!FILES, "set E2E_FILES_URL (SeaweedFS behind Caddy)");
  const preflight = (origin: string) =>
    request.fetch(`${FILES}/${BUCKET}`, {
      method: "OPTIONS",
      headers: { Origin: origin, "Access-Control-Request-Method": "POST" },
    });
  const origin = new URL(baseURL!).origin;
  const allowed = await preflight(origin);
  expect(allowed.status()).toBeLessThan(300);
  // SeaweedFS answers "*" to an allowed origin (no credentials are sent with the presigned POST); S3 echoes it.
  expect([origin, "*"]).toContain(allowed.headers()["access-control-allow-origin"]);
  const other = await preflight("https://evil.example");
  expect(other.ok() && other.headers()["access-control-allow-origin"] !== undefined).toBe(false);
});
