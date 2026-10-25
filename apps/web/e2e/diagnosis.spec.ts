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
  await expect(top.getByTestId("confidence")).toContainText("High confidence");
  await expect(top.getByTestId("explanation")).toContainText("This is the most likely cause.");
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
  await expect(page.getByText("Valve issue", { exact: true })).toBeVisible();
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

  // Request a Mechanic: this session had a red safety alert, so the request is urgent (helpline first).
  await request.click();
  await expect(page).toHaveURL(new RegExp(`/request\\?session=${sessionId}$`));
  await expect(page.getByRole("heading", { name: "Get help now" })).toBeVisible();
  await expect(page.getByTestId("helpline")).toContainText("+91-00000-11111");
  await expect(page.getByTestId("request-car")).toContainText("Maruti Suzuki Swift");
  await expect(page.getByTestId("request-diagnosis")).toContainText("Slow/pinhole puncture");
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await page.getByLabel("Your name", { exact: true }).fill("Asha Verma");
  await page.getByLabel("Mobile number", { exact: true }).fill("12345");
  await page.getByLabel("Area, sector or landmark").fill("Sector 62, Noida");
  await page.getByRole("button", { name: "Send urgent request" }).click();
  await expect(page.getByText(/10-digit Indian mobile/)).toBeVisible();
  await expect(page.getByText(/Tick the box/)).toBeVisible();
  await page.getByLabel("Mobile number", { exact: true }).fill("98765 43210");
  await page.getByRole("checkbox").check();
  await expectNoSideScroll(page);
  await expectTouchTargets(page);
  await page.getByRole("button", { name: "Send urgent request" }).click();
  await expect(page.getByTestId("reference")).toHaveText("IM-TEST1");
  await expect(page.getByText("What happens next")).toBeVisible();
  await expect(page.getByText("Helpline: +91-00000-11111")).toBeVisible();
  expect(fake.requests[0]).toMatchObject({ session_id: sessionId, consent: true, urgent: true, name: "Asha Verma" });

  // The result opens from a shared link in a fresh browser (no saved state).
  const other = await browser.newContext();
  const shared = await other.newPage();
  shared.route("http://localhost:8000/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const answer = fake.handle(req.method(), url.pathname);
    if (answer?.text !== undefined) return route.fulfill({ status: answer.status, body: answer.text, contentType: answer.contentType });
    await route.fulfill(answer ? { status: answer.status, json: answer.json } : { status: 404, body: "" });
  });
  await shared.goto(`/diagnose/${sessionId}/result`);
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
  const fake = await mockApi(page);
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

  // A normal (not urgent) request with every field, prefilled with the typed car.
  await page.getByRole("link", { name: "Request a Mechanic" }).locator("visible=true").click();
  await expect(page.getByRole("heading", { name: "Request a Mechanic" })).toBeVisible();
  await expect(page.getByTestId("request-car")).toContainText("Hindustan Ambassador 2010");
  await page.getByLabel("Your name", { exact: true }).fill("Vikram");
  await page.getByLabel("Mobile number", { exact: true }).fill("+91 70000 12345");
  await page.getByRole("group", { name: "How should we help?" }).getByText("Workshop visit").click();
  await page.getByLabel("Area, sector or landmark").fill("Lajpat Nagar");
  await page.getByLabel("Pincode", { exact: true }).fill("110024");
  await page.getByLabel("Address (optional)").fill("Block C, near the metro");
  await page.getByRole("group", { name: "Preferred time (optional)" }).getByText("Tomorrow morning").click();
  await page.getByLabel("Notes (optional)").fill("Car is old, please bring a battery tester");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Request a Mechanic" }).click();
  await expect(page.getByTestId("reference")).toHaveText("IM-TEST1");
  expect(fake.requests[0]).toMatchObject({
    urgent: false,
    service_type: "workshop",
    pincode: "110024",
    preferred_time: "tomorrow_morning",
    address: "Block C, near the metro",
  });
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

  // Emergency request: helpline first, only the required fields, marked urgent.
  await button.click();
  await expect(page.getByRole("heading", { name: "Get help now" })).toBeVisible();
  await expect(page.getByTestId("helpline")).toContainText("+91-00000-11111");
  await expect(page.getByLabel("Address (optional)")).toHaveCount(0);
  await page.getByLabel("Your name", { exact: true }).fill("Ravi");
  await page.getByLabel("Mobile number", { exact: true }).fill("9876543210");
  await page.getByLabel("Area, sector or landmark").fill("NH-48 near Manesar toll");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Send urgent request" }).click();
  await expect(page.getByTestId("confirmation")).toContainText("(urgent)");
  await expect(page.getByTestId("reference")).toHaveText("IM-TEST1");
});

test("browser Back from the questions shows usable problem tiles again", async ({ page }) => {
  await mockApi(page);
  await pickSwift(page);
  await page.getByRole("button", { name: /^Tyres/ }).click();
  await expect(page.getByText("Question 1 of about 8")).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("button", { name: /^Tyres/ })).toBeEnabled();
});

test("typed replies: what we understood, correcting it, then tapping; the result explains each cause", async ({ page }) => {
  const fake = await mockApi(page);
  await pickSwift(page);
  await page.getByRole("button", { name: /^Tyres/ }).click();
  await expect(page.getByText("Question 1 of about 8")).toBeVisible();

  // Type instead of tapping: the chip says what we understood; the same question stays (no LLM: words never answer).
  const box = page.getByLabel("Or type your answer in your own words");
  await box.fill("hawa 2 din mein kam ho jaati hai");
  await page.getByRole("button", { name: "Send" }).click();
  const chip = page.getByRole("button", { name: /We understood: tyre goes soft again/ });
  await expect(chip).toBeVisible();
  await expect(box).toHaveValue("");
  await expect(page.getByText("Question 1 of about 8")).toBeVisible();
  await expectNoSideScroll(page);
  await expectTouchTargets(page);

  // Tap the chip to correct it: the message comes back to edit and is no longer counted.
  await chip.click();
  await page.getByRole("button", { name: "Edit my message" }).click();
  await expect(box).toHaveValue("hawa 2 din mein kam ho jaati hai");
  await expect(box).toBeFocused();
  await expect(page.getByRole("button", { name: /We understood/ })).toHaveCount(0);
  const sessionId = page.url().split("/").at(-1)!;
  expect(fake.sessions.get(sessionId)!.messages).toEqual([]);

  // Send an edited message, then tap: the message can no longer be corrected.
  await box.fill("nail laga hai, hawa kam ho jaati hai");
  await box.press("Enter"); // a new line, not a send
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("button", { name: /We understood: tyre goes soft again · nail in the tyre/ })).toBeVisible();
  await page.getByRole("button", { name: "The tyre goes soft again after I fill it with air" }).click();
  await expect(page.getByText("Question 2 of about 8")).toBeVisible();
  await expect(page.getByRole("button", { name: /We understood/ })).toHaveCount(0);
  await expect(page.getByText(/We understood: tyre goes soft again · nail in the tyre/)).toBeVisible();
  await page.getByRole("button", { name: "Within hours or days" }).click();

  // Result: confidence word, 3-step meter and reason; streamed explanation; evidence; If this doesn't fix it.
  await expect(page).toHaveURL(/\/result$/);
  const top = page.getByRole("article", { name: "Slow/pinhole puncture" });
  const meter = top.getByTestId("confidence");
  await expect(meter).toContainText("High confidence");
  await expect(meter).toContainText("Your answers point clearly to this cause.");
  await expect(meter.locator("[data-filled]")).toHaveCount(3);
  await expect(top.getByTestId("explanation")).toHaveText(/^This is the most likely cause\. It fits because you said/);
  await expect(top.getByRole("listitem").filter({ hasText: "You answered “Within hours or days”" })).toBeVisible();
  const next = page.getByRole("region", { name: "If this doesn't fix it" }).locator("visible=true");
  await expect(next).toContainText("Ask the mechanic to check: Valve issue.");
  await expect(next).toContainText("Still not fixed? Ask for a full inspection");
  await page.getByText("Valve issue", { exact: true }).click();
  await expect(page.getByText("Doesn't fit: you answered “No” to: Is the valve cap missing?")).toBeVisible();
  await expectNoSideScroll(page);
  await expectTouchTargets(page);
});

test("a typed reply with danger words goes straight to the red banner", async ({ page }) => {
  await mockApi(page);
  await pickSwift(page);
  await page.getByRole("button", { name: /^Tyres/ }).click();
  await page.getByLabel("Or type your answer in your own words").fill("ab bonnet se smoke aa raha hai");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page).toHaveURL(/\/result$/);
  await expect(page.getByTestId("safety-banner").locator("visible=true")).toContainText(
    "Stop the car, switch off the engine and get everyone out.",
  );
});

test("when a cause is uncertain the result says so", async ({ page }) => {
  await mockApi(page);
  await pickSwift(page);
  await page.getByRole("button", { name: /^Tyres/ }).click();
  await page.getByRole("button", { name: "The tyre goes soft again after I fill it with air" }).click();
  await page.getByRole("button", { name: "Not sure" }).click();
  await expect(page.getByRole("region", { name: "We're not certain yet" }).locator("visible=true")).toContainText(
    "Two causes are about equally likely",
  );
});
