import { expect, test } from "@playwright/test";

import { expectNoSideScroll, expectTouchTargets } from "./checks";
import { mockApi } from "./mock-api";

// Phase 5.2: the optional WhatsApp box on the request form, the "Turn on alerts" card and the service worker.
// Subscribing needs a real push service, so that part is covered by the unit tests (src/__tests__/alerts.test.tsx).

test("the service worker is served from the site root", async ({ request }) => {
  const res = await request.get("/sw.js");
  expect(res.ok()).toBe(true);
  expect(res.headers()["content-type"]).toContain("javascript");
  const body = await res.text();
  expect(body).toContain('addEventListener("push"');
  expect(body).toContain("url.origin === self.location.origin"); // only opens our own site
});

test("request form: WhatsApp updates are optional and separate; alerts are offered after sending", async ({ page }) => {
  const fake = await mockApi(page);
  fake.notifications.push_public_key = "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U";
  await page.goto("/request");
  const whatsapp = page.getByRole("checkbox", { name: /updates about my mechanic request on WhatsApp/ });
  await expect(whatsapp).not.toBeChecked();
  await expect(page.getByTestId("whatsapp-consent-text")).toContainText("I can stop them at any time by sending STOP.");
  await page.getByLabel("Your name", { exact: true }).fill("Asha Verma");
  await page.getByLabel("Mobile number", { exact: true }).fill("98765 43210");
  await page.getByRole("group", { name: "How should we help?" }).getByText("At my location").click();
  await page.getByLabel("Area, sector or landmark").fill("Sector 62, Noida");
  await page.getByLabel("Pincode").fill("201309");
  await page.getByRole("checkbox", { name: /Instant Mechanic's team may use/ }).check();
  await whatsapp.check();
  await expectTouchTargets(page);
  await page.getByRole("button", { name: "Request a Mechanic" }).click();

  await expect(page.getByTestId("reference")).toHaveText("IM-TEST1");
  expect(fake.requests[0]).toMatchObject({ whatsapp_optin: true, whatsapp_consent_version: "whatsapp-customer-v1" });
  // Headless Chromium always reports notifications as blocked (even when granted), so the card shows how to allow
  // them; a normal browser shows the "Turn on alerts" button (unit tests cover turning them on and off).
  const alerts = page.getByTestId("alerts");
  await expect(alerts).toContainText(/Get an alert when your mechanic is assigned|Alerts are blocked for this site/);
  await expectNoSideScroll(page);
});

test("no alerts card when the server has no push key", async ({ page }) => {
  await mockApi(page);
  await page.goto("/request");
  await page.getByLabel("Your name", { exact: true }).fill("Asha Verma");
  await page.getByLabel("Mobile number", { exact: true }).fill("98765 43210");
  await page.getByRole("group", { name: "How should we help?" }).getByText("At my location").click();
  await page.getByLabel("Area, sector or landmark").fill("Sector 62, Noida");
  await page.getByLabel("Pincode").fill("201309");
  await page.getByRole("checkbox", { name: /Instant Mechanic's team may use/ }).check();
  await page.getByRole("button", { name: "Request a Mechanic" }).click();
  await expect(page.getByTestId("reference")).toHaveText("IM-TEST1");
  await expect(page.getByTestId("alerts")).toHaveCount(0);
});
