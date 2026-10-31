import { expect, type Page, test } from "@playwright/test";

import { PARTS_ROUTES } from "../src/__tests__/parts-data";
import { expectNoSideScroll, expectTouchTargets } from "./checks";
import { mockApi } from "./mock-api";

/** Parts and estimates on top of the diagnosis mock (routes added later run first). */
async function mockParts(page: Page) {
  await page.route("http://localhost:8000/api/**", async (route) => {
    const url = new URL(route.request().url());
    const hit = PARTS_ROUTES.find(([prefix]) => url.pathname.startsWith(prefix));
    if (!hit) return route.fallback();
    const body = hit[1](url);
    if (body === "missing") return route.fulfill({ status: 404, body: "not found" });
    return route.fulfill({ json: body });
  });
}

async function resultForSwift(page: Page) {
  await mockApi(page);
  await mockParts(page);
  await page.goto("/diagnose");
  await page.getByLabel("Search for your car").fill("swift");
  await page.getByRole("button", { name: /Maruti Suzuki Swift/ }).click();
  await page.getByRole("button", { name: /^Tyres/ }).click();
  await page.getByRole("button", { name: "The tyre goes soft again after I fill it with air" }).click();
  await page.getByRole("button", { name: "Not sure" }).click();
  await expect(page).toHaveURL(/\/result$/);
}

test("result: parts you may need (fits / fit not verified), estimated cost, your area, compare and detail", async ({
  page,
}) => {
  await resultForSwift(page);
  const top = page.getByRole("article", { name: "Slow/pinhole puncture" });

  // Estimated cost from /api/estimates: range, breakdown, metro label, one calm verification line.
  await expect(top.getByTestId("estimate-total")).toHaveText("₹600");
  await expect(top.getByTestId("estimate-breakdown")).toContainText("Labour₹150");
  await expect(top.getByTestId("labour-basis")).toHaveText("Delhi NCR metro estimate");
  await expect(page.getByText("Prices are being verified with our mechanics.")).toHaveCount(1);
  await top.getByText("Where these prices come from").click();
  await expect(top.getByTestId("estimate-sources")).toContainText("Checked 22 Oct 2026");

  // Your area: a zone re-fetches the estimate with the zone's labour rate.
  await top.getByText("Gurugram", { exact: true }).click();
  await expect(top.getByTestId("estimate-total")).toHaveText("₹750 – ₹1,150");
  await expect(top.getByTestId("labour-basis")).toHaveText("Labour rate for Gurugram");

  // Parts you may need: one listed for the car, one whose fit is not verified.
  const parts = page.getByRole("region", { name: "Parts you may need" });
  await expect(parts.getByTestId("part-card")).toHaveCount(3);
  const valve = parts.getByRole("article", { name: "Tyre valve (tubeless)" });
  await expect(valve.getByTestId("fit-badge")).toHaveText("Fits your car");
  await expect(valve.getByText("Genuine (OEM)")).toBeVisible();
  const kit = parts.getByRole("article", { name: "Puncture repair kit (plug type)" });
  await expect(kit.getByTestId("fit-badge")).toHaveText("Fit not verified for your car");
  await expect(kit.getByTestId("part-price")).toHaveText("₹250 – ₹1,400");
  await expect(parts.getByRole("article", { name: "Tyre sealant" }).getByTestId("part-price")).toHaveText("₹12,34,567");

  await expectNoSideScroll(page);
  await expectTouchTargets(page);

  // Compare two parts side by side.
  await valve.getByLabel("Compare").check();
  await kit.getByLabel("Compare").check();
  await parts.getByRole("link", { name: "Compare 2 parts" }).click();
  await expect(page).toHaveURL(/\/parts\/compare\?ids=101,102&variant_id=16$/);
  const table = page.getByTestId("compare-table");
  await expect(table.getByRole("columnheader")).toHaveCount(2);
  await expect(table.getByTestId("fit-badge")).toHaveText(["Fits your car", "Fit not verified for your car"]);
  await expectNoSideScroll(page); // the table scrolls inside its own box on a phone

  // A part's own page.
  await table.getByRole("link", { name: "Tyre valve (tubeless)" }).click();
  await expect(page).toHaveURL(/\/parts\/101\?variant_id=16$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Tyre valve (tubeless)");
  await expect(page.getByTestId("fit-badge")).toHaveText("Fits your car");
  await expect(page.getByText("Maruti Suzuki Swift 2024–now")).toBeVisible();
  await expectNoSideScroll(page);
});

test("a cause without enough price data shows Price on inspection and Request a Mechanic", async ({ page }) => {
  await resultForSwift(page);
  const others = page.getByRole("region", { name: "Other possible causes" });
  await others.getByText("Valve issue").click();
  const card = others.getByTestId("estimate").first();
  await expect(card.getByTestId("estimate-total")).toHaveText("Price on inspection");
  await expect(card.getByRole("link", { name: "Request a Mechanic" })).toBeVisible();
});

test("a pincode outside Delhi NCR keeps the metro estimate", async ({ page }) => {
  await resultForSwift(page);
  const top = page.getByRole("article", { name: "Slow/pinhole puncture" });
  await top.getByLabel("Or your pincode").fill("400001");
  await top.getByRole("button", { name: "Use pincode" }).click();
  await expect(page.getByTestId("area-note")).toContainText("not in our Delhi NCR zones");
  await expect(top.getByTestId("labour-basis")).toHaveText("Delhi NCR metro estimate");
});

test("a part opened without a car shows no fit badge", async ({ page }) => {
  await mockApi(page);
  await mockParts(page);
  await page.goto("/parts/102");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Puncture repair kit (plug type)");
  await expect(page.getByTestId("fit-badge")).toHaveCount(0);
  await expect(page.getByText(/Pick your car in a diagnosis/)).toBeVisible();
});
