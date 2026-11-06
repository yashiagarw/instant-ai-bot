import { expect, test } from "@playwright/test";

import { CODE, FakeMechanic } from "../src/__tests__/fake-mechanic";
import { expectNoSideScroll } from "./checks";
import { mockApi } from "./mock-api";

// The mechanic app (/m) on a phone and a desktop, with the API mocked (src/__tests__/fake-mechanic.ts).
// Small Android phone: 360 x 640.
test.use({ viewport: { width: 360, height: 640 } });

/** Every visible control in the app is a big target (at least 48 px; the app aims for 56). */
async function expectBigTargets(page: import("@playwright/test").Page) {
  const small = await page.evaluate(() =>
    [...document.querySelectorAll("main button, main a, main input, nav a")]
      .filter((el) => (el as HTMLElement).offsetParent !== null)
      .map((el) => ({ text: el.textContent?.trim().slice(0, 30), h: el.getBoundingClientRect().height }))
      .filter((t) => t.h < 48),
  );
  expect(small).toEqual([]);
}

test("installable: its own manifest and icons, and an offline page", async ({ request }) => {
  const m = await request.get("/m/manifest.webmanifest");
  expect(m.headers()["content-type"]).toContain("application/manifest+json");
  const manifest = await m.json();
  expect(manifest).toMatchObject({ start_url: "/m", scope: "/m", display: "standalone", short_name: "IM Mechanic" });
  for (const icon of manifest.icons) expect((await request.get(icon.src)).ok()).toBe(true);
  const site = await (await request.get("/manifest.webmanifest")).json();
  expect(site).toMatchObject({ start_url: "/", short_name: "Instant Mechanic" });
  const offline = await request.get("/m/offline.html");
  expect(await offline.text()).toContain("आप ऑफ़लाइन हैं");
});

test("the /m pages link the mechanic manifest; the customer site links its own", async ({ page }) => {
  await mockApi(page, new FakeMechanic());
  await page.goto("/m/login");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/m/manifest.webmanifest");
  await page.goto("/");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", /^\/manifest\.webmanifest/);
});

test("sign in, take an offer, travel, work and record the fault, in Hindi on a small phone", async ({ page }) => {
  const api = await mockApi(page, new FakeMechanic());
  await page.goto("/m");
  await expect(page).toHaveURL(/\/m\/login$/);
  await page.getByLabel("मोबाइल नंबर").fill("90000 00011");
  await page.getByRole("button", { name: "कोड भेजें" }).click();
  await page.getByLabel("6 अंकों का कोड").fill(CODE);
  await page.getByRole("button", { name: "साइन इन" }).click();

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("नमस्ते, Ravi");
  await expectNoSideScroll(page);
  await expectBigTargets(page);
  await page.getByTestId("offers-link").click();
  const offer = page.getByTestId("offer");
  await expect(offer).toContainText("Delhi, pincode 110017");
  await expect(offer).not.toContainText("B-12");
  await expectNoSideScroll(page);
  await expectBigTargets(page);
  await offer.getByRole("button", { name: "काम लें" }).click();

  await expect(page).toHaveURL(/\/m\/jobs\/41$/);
  await expect(page.getByTestId("job-address")).toHaveText("B-12, 2nd floor, Malviya Nagar, 110017");
  await expect(page.getByTestId("job-phone")).toHaveText("+91******1234");
  await page.getByRole("button", { name: "30 मिनट" }).click();
  await expect(page.getByRole("status")).toHaveText("ग्राहक को बता दिया: लगभग 30 मिनट");
  await page.getByRole("button", { name: "निकल रहा हूँ" }).click();
  await page.getByRole("button", { name: "पहुँच गया" }).click();
  await page.getByRole("button", { name: "काम शुरू" }).click();
  await expectNoSideScroll(page);
  await expectBigTargets(page);
  await page.getByRole("radio", { name: /बैटरी कमज़ोर है/ }).click();
  await page.getByRole("button", { name: "पूरा करें और भेजें" }).click();
  await expect(page.getByRole("status")).toContainText("काम पूरा हुआ");
  expect(api.outcome).toMatchObject({ status: "completed", confirmed_fault_key: "F08-BT-01" });
});

test("profile: off duty and English", async ({ page }) => {
  const api = await mockApi(page, new FakeMechanic());
  api.signedIn = true;
  await page.goto("/m/profile");
  await page.getByRole("radio", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Language" })).toBeVisible();
  await page.getByRole("switch", { name: "Go off duty" }).click();
  await expect(page.getByTestId("duty-pill")).toHaveText("Off duty");
  expect(api.onDuty).toBe(false);
  await page.reload(); // the language is remembered
  await expect(page.getByRole("heading", { name: "Language" })).toBeVisible();
  await expectBigTargets(page);
});
