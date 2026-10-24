import { expect, type Page, test } from "@playwright/test";

import { expectNoSideScroll, expectTouchTargets } from "./checks";
import { mockApi } from "./mock-api";

async function savedVehicle(page: Page) {
  return page.evaluate(() => JSON.parse(sessionStorage.getItem("im.diagnosis.vehicle") ?? "null"));
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("landing page: hero, tiles, emergency row and disclaimer", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Know what's wrong with your car");
  await expect(page.getByRole("link", { name: "Tyres" })).toHaveAttribute("href", "/diagnose?topic=tyres");
  await expect(page.getByRole("link", { name: "Flat tyre" })).toBeVisible();
  await expect(page.getByText(/not a replacement for a professional inspection/i)).toBeVisible();
  await expectNoSideScroll(page);
  await expectTouchTargets(page);
});

test("listed car: search, then make, model, year, fuel and gearbox", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /start free diagnosis/i }).click();
  await expect(page).toHaveURL(/\/diagnose$/);
  await expect(page.getByRole("listitem").filter({ hasText: "Car" }).first()).toHaveAttribute("aria-current", "step");

  // Search box (debounced) shows the matching variant.
  await page.getByLabel("Search for your car").fill("swift");
  await expect(page.getByRole("button", { name: /Maruti Suzuki Swift/ })).toBeVisible();
  await page.getByLabel("Search for your car").fill("");

  // Make tiles → model → year with the keyboard → version.
  await page.getByRole("button", { name: "Maruti Suzuki", exact: true }).click();
  await page.getByRole("button", { name: "Swift", exact: true }).click();
  const years = page.getByRole("group", { name: "Year" });
  await years.getByRole("radio", { name: "2021" }).focus();
  await page.keyboard.press("ArrowRight"); // 2020: native radios move and select with arrow keys
  await expect(years.getByRole("radio", { name: "2020" })).toBeChecked();
  await expect(page.getByRole("group", { name: "Fuel" }).getByRole("radio", { name: "Petrol" })).toBeChecked();
  await page.getByRole("group", { name: "Which version?" }).locator("label", { hasText: "Petrol MT ZXi" }).click();
  await expect(page.getByText(/Price range: ₹10-25 lakh/)).toBeVisible();
  await expectNoSideScroll(page);
  await expectTouchTargets(page);

  await page.getByRole("button", { name: /this is my car/i }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Problem" })).toHaveAttribute("aria-current", "step");
  await expect(page.getByTestId("chosen-car")).toHaveText("Maruti Suzuki Swift 2020 · Petrol MT ZXi");
  expect(await savedVehicle(page)).toMatchObject({ kind: "listed", variant_id: 11, price_segment: "mid" });
});

test("unlisted car: typed details, fuel, gearbox and rough price", async ({ page }) => {
  await page.goto("/diagnose?topic=tyres");
  await page.getByRole("button", { name: /my car isn.t listed/i }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Type the make, for example Maruti Suzuki.")).toBeVisible();
  await expect(page.getByLabel("Make")).toBeFocused();

  await page.getByLabel("Make").fill("Hindustan");
  await page.getByLabel("Model").fill("Ambassador");
  await page.getByLabel("Year").fill("2010");
  await page.getByRole("group", { name: "Fuel" }).getByText("Diesel", { exact: true }).click();
  await page.getByRole("group", { name: "Gearbox" }).getByText("Manual", { exact: true }).click();
  await page.getByRole("group", { name: "Roughly what did the car cost new?" }).getByText("Not sure", { exact: true }).click();
  await expectNoSideScroll(page);
  await expectTouchTargets(page);
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByTestId("chosen-car")).toHaveText("Hindustan Ambassador 2010");
  await expect(page.getByText(/not sure \(we'll show general guidance\)/)).toBeVisible();
  expect(await savedVehicle(page)).toEqual({
    kind: "unlisted",
    label: "Hindustan Ambassador 2010",
    unlisted: { make: "Hindustan", model: "Ambassador", year: 2010, fuel: "diesel", transmission: "mt", price_segment: null },
  });
});
