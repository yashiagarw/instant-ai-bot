import { expect, type Page, test } from "@playwright/test";

import { expectNoSideScroll, expectTouchTargets } from "./checks";
import { mockApi } from "./mock-api";

async function pickSwift(page: Page) {
  await page.goto("/diagnose");
  await page.getByLabel("Search for your car").fill("swift");
  await page.getByRole("button", { name: /Maruti Suzuki Swift/ }).click();
  await expect(page.getByRole("heading", { name: "What's the problem?" })).toBeVisible();
}

test("full diagnosis: problem tile, questions with a safety alert and Back, result, feedback, shared link", async ({
  page,
  browser,
  isMobile,
}) => {
  const fake = await mockApi(page);
  await pickSwift(page);

  // Problem step: tiles with Hindi labels and Beta, the emergency row, free text.
  const tyres = page.getByRole("button", { name: /^Tyres/ });
  await expect(tyres).toContainText("टायर");
  await expect(page.getByRole("button", { name: /Locked out/ })).toContainText("Beta");
  await expect(page.getByRole("button", { name: /EV & hybrid/ })).toHaveCount(0);
  await expect(page.getByLabel("Describe what's happening")).toBeVisible();
  await expectNoSideScroll(page);
  await expectTouchTargets(page);
  await tyres.click();

  // Questions: car pinned at the top, progress, a safety answer shows the red banner at once.
  await expect(page).toHaveURL(/\/diagnose\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("car-summary").locator("visible=true")).toContainText("Maruti Suzuki Swift");
  await expect(page.getByText("Question 1 of about 8")).toBeVisible();
  await page.getByRole("button", { name: "It feels unsafe to drive" }).click();
  await expect(page.getByTestId("safety-banner").locator("visible=true")).toContainText("Slow down and stop in a safe place");
  await expect(page.getByText("Question 2 of about 8")).toBeVisible();
  await expect(page.locator("#question-heading")).toBeFocused();

  // Back to change the previous answer.
  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByText("Your earlier answer is highlighted")).toBeVisible();
  await page.getByRole("button", { name: "The tyre goes soft again after I fill it with air" }).click();
  await expect(page.getByText("Question 2 of about 8")).toBeVisible();
  await expectTouchTargets(page);
  await page.getByRole("button", { name: "Not sure" }).click();

  // Result.
  await expect(page).toHaveURL(/\/result$/);
  await expect(page.getByTestId("safety-banner").locator("visible=true")).toBeVisible(); // the alert from the answer stays first
  await expect(page.getByTestId("coverage").locator("visible=true")).toContainText("Segment estimate");
  const top = page.getByRole("article", { name: "Slow/pinhole puncture" });
  await expect(top.getByText("Why we think this")).toBeVisible();
  await expect(top.getByTestId("roadside")).toContainText("Roadside check, then a garage");
  await expect(top.getByTestId("cost-total")).toHaveText("₹230");
  await expect(top.getByText("Price checked 12 Oct 2026")).toBeVisible();
  await expect(top.getByText("Illustration", { exact: true })).toBeVisible();
  await expect(top.getByText("How it's checked")).toHaveCount(0);
  await expect(top.getByText("Parts are replaced only when the test confirms.")).toBeHidden();
  await top.getByRole("button", { name: "Show all 7 steps" }).click();
  await expect(top.getByText("Parts are replaced only when the test confirms.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Safety tips" }).locator("visible=true")).toContainText(
    "Drive slowly to the nearest tyre shop.",
  );
  await expect(page.getByText("Valve issue")).toBeVisible();
  await expect(page.getByText("Change the valve core.")).toBeHidden(); // collapsed
  await expect(page.getByTestId("disclaimer").locator("visible=true")).toContainText("not a replacement for a professional inspection");
  await expectNoSideScroll(page);

  // Request a Mechanic: stuck to the bottom of the screen on mobile, in the page on desktop.
  const request = page.getByRole("link", { name: "Request a Mechanic" }).locator("visible=true");
  await expect(request).toHaveCount(1);
  const box = (await request.boundingBox())!;
  const viewport = page.viewportSize()!;
  if (isMobile) expect(box.y + box.height).toBeGreaterThan(viewport.height - 80);
  expect(box.height).toBeGreaterThanOrEqual(44);

  await page.getByRole("button", { name: "Yes" }).click();
  await page.getByRole("button", { name: "Send feedback" }).click();
  await expect(page.getByText("Thanks for your feedback.")).toBeVisible();
  const sessionId = page.url().split("/").at(-2)!;
  expect(fake.sessions.get(sessionId)!.feedback).toEqual([{ helpful: true, comment: null }]);

  // The result opens from a shared link in a fresh browser (no saved state).
  const other = await browser.newContext();
  const shared = await other.newPage();
  shared.route("http://localhost:8000/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const answer = fake.handle(req.method(), url.pathname);
    await route.fulfill(answer ? { status: answer.status, json: answer.json } : { status: 404, body: "" });
  });
  await shared.goto(page.url());
  await expect(shared.getByRole("article", { name: "Slow/pinhole puncture" })).toBeVisible();
  await other.close();
});

test("safety case: smoke in the description shows the red banner first on the result", async ({ page }) => {
  await mockApi(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await pickSwift(page);
  await page.getByLabel("Describe what's happening").fill("bonnet se smoke aa raha hai");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/result$/);
  const banner = page.getByTestId("safety-banner").locator("visible=true");
  await expect(banner).toContainText("Stop the car, switch off the engine and get everyone out.");
  await expect(banner).toHaveCSS("background-color", "rgb(198, 40, 40)");
  const first = await page.locator("main [data-testid]").locator("visible=true").first().getAttribute("data-testid");
  expect(first).toBe("safety-banner");
  await expect(page.getByRole("link", { name: "Request a Mechanic" }).locator("visible=true")).toBeVisible();
});

test("unlisted car without a price range gets General guidance and no cost", async ({ page }) => {
  await mockApi(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/diagnose");
  await page.getByRole("button", { name: /my car isn.t listed/i }).click();
  await page.getByLabel("Make").fill("Hindustan");
  await page.getByLabel("Model").fill("Ambassador");
  await page.getByLabel("Year").fill("2010");
  await page.getByRole("group", { name: "Fuel" }).getByText("Diesel", { exact: true }).click();
  await page.getByRole("group", { name: "Gearbox" }).getByText("Manual", { exact: true }).click();
  await page.getByRole("group", { name: "Roughly what did the car cost new?" }).getByText("Not sure", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByRole("button", { name: /^Tyres/ }).click();
  const card = page.getByRole("region", { name: /What problem are you facing/ });
  await expect(card).toBeVisible();
  // Reduced motion: the question card does not animate.
  expect(await card.evaluate((el) => getComputedStyle(el).animationName)).toBe("none");
  await page.getByRole("button", { name: "One tyre looks a little soft" }).click();
  await expect(page.getByText("Question 2 of about 8")).toBeVisible();
  await page.getByRole("button", { name: "Within hours or days" }).click();

  await expect(page).toHaveURL(/\/result$/);
  await expect(page.getByTestId("coverage").locator("visible=true")).toContainText("General guidance");
  await expect(page.getByTestId("car-summary").locator("visible=true")).toContainText("Hindustan Ambassador 2010");
  await expect(page.getByText(/can't estimate the cost without your car's price range/).first()).toBeVisible();
  await expect(page.getByTestId("cost-total").locator("visible=true")).toHaveCount(0);
});

test("fast-track topic: at most 3 questions, then safety tips and a large Request a Mechanic button", async ({ page }) => {
  await mockApi(page);
  await pickSwift(page);
  await page.getByRole("button", { name: /Flat tyre/ }).click();
  await expect(page.getByText("Question 1 of about 3")).toBeVisible();
  await page.getByRole("button", { name: "No, it is on the road" }).click();
  await expect(page).toHaveURL(/\/result$/);
  const tips = page.getByRole("region", { name: "Stay safe while help comes" });
  await expect(tips.getByText("Switch on the hazard lights.")).toBeVisible();
  const button = tips.getByRole("link", { name: "Request a Mechanic" });
  await expect(button).toBeVisible();
  expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(56);
});

test("browser Back from the questions shows usable problem tiles again", async ({ page }) => {
  await mockApi(page);
  await pickSwift(page);
  await page.getByRole("button", { name: /^Tyres/ }).click();
  await expect(page.getByText("Question 1 of about 8")).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("button", { name: /^Tyres/ })).toBeEnabled();
});
