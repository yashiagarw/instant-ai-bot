import { expect, test } from "@playwright/test";

import { expectNoSideScroll, expectTouchTargets } from "./checks";

// Against the real backend and database (not mocked), with the LLM off. Opt-in, on its own ports so a running
// `pnpm dev` / API keeps working:
//   cd backend && LLM_PROVIDER=none WEB_ORIGIN=http://localhost:3110 uv run uvicorn app.main:app --port 8010
//   cd apps/web && E2E_LIVE_API=1 E2E_PORT=3110 NEXT_PUBLIC_API_URL=http://localhost:8010 \
//     pnpm exec playwright test e2e/live.spec.ts
// It creates real sessions in that database.
test.skip(!process.env.E2E_LIVE_API, "live API test: set E2E_LIVE_API=1 with the backend running (see the top)");
test.setTimeout(120_000);

const WORDS = /[A-Za-z']+/g;

test("live, LLM off: Alto K10 battery flow with a typed reply, a correction and template explanations", async ({ page }) => {
  await page.goto("/diagnose");
  await page.getByLabel("Search for your car").fill("alto k10 petrol");
  await page.getByRole("button", { name: /Maruti Suzuki Alto K10/ }).first().click();
  await page.getByRole("button", { name: /Battery, lights & warning lights/ }).click();
  await expect(page).toHaveURL(/\/diagnose\/[0-9a-f-]{36}$/, { timeout: 30_000 });

  // Routing between the tile's categories, when asked.
  const battery = page.getByRole("button", { name: "Battery", exact: true });
  if (await battery.isVisible().catch(() => false)) await battery.click();

  // A typed reply: what we understood (the engine's own search), then take it back and send it again.
  const box = page.getByLabel("Or type your answer in your own words");
  await box.fill("battery jaldi down ho jaati hai, self slow hai");
  await page.getByRole("button", { name: "Send" }).click();
  const chip = page.getByRole("button", { name: /We understood|We added this to your description/ });
  await expect(chip).toBeVisible({ timeout: 30_000 });
  await expectNoSideScroll(page);
  await expectTouchTargets(page);
  await chip.click();
  await page.getByRole("button", { name: "Edit my message" }).click();
  await expect(box).toHaveValue("battery jaldi down ho jaati hai, self slow hai");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("button", { name: /We understood|We added this/ })).toBeVisible();

  // Answer until the result: "Not sure" where offered, otherwise the first option.
  for (let i = 0; i < 12 && !/\/result$/.test(page.url()); i++) {
    const heading = page.locator("#question-heading");
    if (!(await heading.isVisible().catch(() => false))) {
      await page.waitForTimeout(500);
      continue;
    }
    const progress = () =>
      page.getByText(/Question \d+ of about \d+/).textContent({ timeout: 500 }).catch(() => null); // gone on the result
    const before = await progress();
    const notSure = page.getByRole("button", { name: "Not sure" });
    if (await notSure.isVisible()) await notSure.click();
    else await page.locator("section[aria-labelledby='question-heading'] li button").first().click();
    await expect.poll(async () => /\/result$/.test(page.url()) || (await progress()) !== before).toBe(true);
  }
  await expect(page).toHaveURL(/\/result$/, { timeout: 30_000 });

  // The result: confidence word with the meter and reason, a template explanation, evidence, next steps.
  const top = page.getByRole("article").first();
  await expect(top.getByTestId("confidence")).toContainText(/(High|Medium|Low) confidence/);
  const explanation = top.getByTestId("explanation");
  await expect(explanation).toHaveAttribute("data-source", "template", { timeout: 15_000 });
  await expect(explanation).toHaveText(/^This (is|could)/);
  await expect(top).not.toContainText("Start-Stop"); // an Alto K10 has no start-stop: never the top cause
  await expect(page.getByRole("region", { name: "If this doesn't fix it" }).locator("visible=true")).toContainText(
    "Still not fixed? Ask for a full inspection",
  );

  // Safety tips are full, calm sentences: no fragments, no workshop-only instructions.
  const tips = page.getByRole("region", { name: "Safety tips" }).locator("visible=true").getByRole("listitem");
  for (const tip of await tips.allTextContents()) {
    expect(tip.match(WORDS)?.length ?? 0, tip).toBeGreaterThanOrEqual(5);
    expect(tip, tip).toMatch(/[.?]$/);
    expect(tip, tip).not.toMatch(/\b(AGM setting|eye protection|gloves|stands)\b/i);
  }
  await expect(page.getByTestId("disclaimer").locator("visible=true")).toContainText("not a replacement");
  await expectNoSideScroll(page);
});
