// Phase 5.5: the 3D car (and when it is skipped), motion, Hindi pages. The API is mocked (mock-api.ts).
import { expect, type Page, test } from "@playwright/test";

import { FakeDiagnosis } from "../src/__tests__/fake-diagnosis";
import { expectNoSideScroll } from "./checks";
import { mockApi } from "./mock-api";

// WebGL in headless Chromium (software rendering), so the 3D path really runs.
test.use({ launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] } });

/** Content-Security-Policy violations and page errors while the test runs. */
function watch(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(String(e)));
  page.on("console", (m) => {
    if (/Content Security Policy|Refused to/i.test(m.text())) problems.push(m.text());
  });
  const models: string[] = [];
  page.on("request", (r) => {
    if (/car\.glb|\/draco\//.test(r.url())) models.push(r.url());
  });
  return { problems, models };
}

/** Pretend to be a device where 3D must be skipped (before any page script runs). */
async function device(page: Page, nav: { deviceMemory?: number; connection?: object }) {
  await page.addInitScript((n) => {
    for (const [k, v] of Object.entries(n)) Object.defineProperty(Navigator.prototype, k, { get: () => v, configurable: true });
  }, nav);
}

test("landing: the picture first, the 3D car once the visitor uses the page, within the CSP", async ({ page }) => {
  await mockApi(page);
  const w = watch(page);
  await page.goto("/");
  await page.waitForLoadState("load");
  const hero = page.getByTestId("hero-car");
  await expect(hero.getByRole("img", { name: /orange car/ })).toBeVisible(); // the static picture is there at once
  await page.waitForTimeout(1500);
  expect(w.models).toEqual([]); // nothing 3D before the visitor does anything
  await page.mouse.wheel(0, 40); // first scroll
  await expect(hero).toHaveAttribute("data-3d", "ready", { timeout: 20_000 });
  await expect(hero.locator("canvas")).toBeVisible();
  expect(w.models.some((u) => u.endsWith("/3d/car.glb"))).toBe(true);
  expect(w.models.filter((u) => u.includes("/draco/")).every((u) => u.startsWith("http://localhost"))).toBe(true);
  expect(w.problems).toEqual([]);
  await expectNoSideScroll(page);
});

for (const [name, setup] of [
  ["a slow connection", { connection: { effectiveType: "3g", saveData: false } }],
  ["Save-Data", { connection: { effectiveType: "4g", saveData: true } }],
  ["a low-memory phone", { deviceMemory: 2 }],
] as const) {
  test(`no 3D on ${name}: the picture stays and nothing 3D is downloaded`, async ({ page }) => {
    await mockApi(page);
    await device(page, setup);
    const w = watch(page);
    await page.goto("/");
    await page.waitForLoadState("load");
    await page.mouse.wheel(0, 40);
    await page.waitForTimeout(3000);
    await expect(page.getByTestId("hero-car")).toHaveAttribute("data-3d", "off");
    await expect(page.getByTestId("hero-car").locator("canvas")).toHaveCount(0);
    expect(w.models).toEqual([]);
  });
}

test("no 3D with reduced motion", async ({ browser }) => {
  const ctx = await browser.newContext({ reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await mockApi(page);
  const w = watch(page);
  await page.goto("/");
  await page.waitForLoadState("load");
  await page.mouse.wheel(0, 40);
  await page.waitForTimeout(3000);
  await expect(page.getByTestId("hero-car")).toHaveAttribute("data-3d", "off");
  expect(w.models).toEqual([]);
  await ctx.close();
});

function hindiNames(fake: FakeDiagnosis) {
  const handle = fake.handle.bind(fake);
  fake.handle = (method, path, body) => {
    const out = handle(method, path, body);
    if (out && method === "GET" && path.endsWith("/result")) {
      const r = out.json as { ranked: { name_hi?: string | null }[] };
      r.ranked = r.ranked.map((f, i) => ({ ...f, name_hi: i === 0 ? "टायर धीरे-धीरे पंक्चर" : null }));
    }
    return out;
  };
  return fake;
}

test("result: the diagnosed system on the 3D car; Hindi page with reviewed Hindi name, English safety", async ({ page }) => {
  const fake = hindiNames(await mockApi(page));
  const s = fake.handle("POST", "/api/diagnosis/sessions", { vehicle: { variant_id: 16 }, topic_id: "tyres" })!;
  const id = (s.json as { session_id: string }).session_id;
  const w = watch(page);
  await page.goto(`/hi/diagnose/${id}/result`);
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page.getByRole("heading", { level: 1, name: "आपका नतीजा" })).toBeVisible();
  await expect(page.locator("#top-cause")).toHaveText("टायर धीरे-धीरे पंक्चर");
  await expect(page.locator("#top-cause")).toHaveAttribute("lang", "hi");
  await expect(page.getByTestId("disclaimer")).toContainText("अनुमान");
  // The cost counts up and ends on the real price (no /api/estimates in the mock: the result's own cost card).
  await expect(page.getByTestId("cost-total").first()).toHaveText("₹230", { timeout: 5000 });

  const card = page.getByTestId("result-car");
  await expect(card).toContainText("टायर"); // "Highlighted in orange: Tyres"
  await expect(card).toHaveAttribute("data-highlight", /tyre_fl/);
  await card.scrollIntoViewIfNeeded();
  await expect(card).toHaveAttribute("data-3d", "ready", { timeout: 20_000 });
  expect(w.problems).toEqual([]);
  await expectNoSideScroll(page);
});

test("the question chat never shows 3D", async ({ page }) => {
  const fake = await mockApi(page);
  const s = fake.handle("POST", "/api/diagnosis/sessions", { vehicle: { variant_id: 16 }, topic_id: "tyres" })!;
  const id = (s.json as { session_id: string }).session_id;
  const w = watch(page);
  await page.goto(`/diagnose/${id}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.waitForTimeout(3000);
  await expect(page.locator("canvas")).toHaveCount(0);
  expect(w.models).toEqual([]);
});

test("language switch: English -> Hindi keeps the page and the topic; Hindi -> English", async ({ page }) => {
  await mockApi(page);
  await page.goto("/diagnose?topic=tyres");
  await page.getByTestId("language-switch").click();
  await expect(page).toHaveURL(/\/hi\/diagnose\?topic=tyres$/);
  await expect(page.getByRole("heading", { level: 1, name: "आप कौन-सी कार चलाते हैं?" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("im.lang"))).toBe("hi");
  await page.getByTestId("language-switch").click();
  await expect(page).toHaveURL(/\/diagnose\?topic=tyres$/);
  await expect(page.getByRole("heading", { level: 1, name: "Which car do you drive?" })).toBeVisible();
  await page.goto("/request");
  await expect(page.getByTestId("language-switch")).toHaveCount(0); // English-only page
});
