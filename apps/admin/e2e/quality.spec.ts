import { expect, test } from "@playwright/test";

import { FakeAdmin } from "./fake-admin";
import { SESSION } from "./fake-quality";

test("overview: requests today, unassigned safety-critical in red, diagnoses, and LLM off", async ({ page }) => {
  await new FakeAdmin().as("boss@im.test").install(page);
  await page.goto("/");
  await expect(page.getByTestId("requests-today")).toContainText("5");
  await expect(page.getByRole("list", { name: "Requests today by status" })).toContainText("New: 3");
  await expect(page.getByTestId("diagnoses-today")).toContainText("12");
  await expect(page.getByTestId("diagnoses-today")).toContainText("9 finished · 2 safety alerts");
  await expect(page.getByTestId("llm-today")).toContainText("LLM off");
  await expect(page.getByTestId("llm-today")).not.toContainText("$");

  const rows = page.getByTestId("unassigned-row");
  await expect(rows).toHaveCount(2);
  const critical = rows.first().getByRole("link");
  await expect(critical).toContainText("IM-SAFE03");
  await expect(critical).toContainText("Safety-critical");
  await expect(critical).toHaveCSS("background-color", "rgb(198, 40, 40)"); // danger red
  await expect(rows.nth(1).getByRole("link")).not.toHaveCSS("background-color", "rgb(198, 40, 40)");
  await critical.click();
  await expect(page).toHaveURL(/\/requests\/11111111-0000-4000-8000-000000000003$/);
});

test("overview: each role sees only its parts; LLM spend shows when an LLM is on", async ({ page }) => {
  const fake = await new FakeAdmin().as("agent@im.test").install(page);
  await page.goto("/");
  await expect(page.getByTestId("requests-today")).toBeVisible();
  await expect(page.getByTestId("diagnoses-today")).toHaveCount(0);
  await expect(page.getByTestId("llm-today")).toHaveCount(0);

  fake.as("content@im.test");
  fake.quality.llm = { live: true, calls: 14, cost_usd: 0.4213, daily_cap_usd: 2, failures: 1, failure_rate: 0.0714,
    fallbacks: 2, fallback_rate: 0.1429, by_outcome: { ok: 12, timeout: 1, spend_cap: 1 } }; // prettier-ignore
  await page.reload();
  await expect(page.getByTestId("requests-today")).toHaveCount(0);
  await expect(page.getByTestId("llm-today")).toContainText("$0.42");
  await expect(page.getByTestId("llm-today")).toContainText("$0.42 of $2.00 a day · 14 calls");
});

test("quality: safety, latest eval with real cases apart, confirmed accuracy with the 30-case rule, LLM off", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/quality");
  const danger = page.getByTestId("danger-missed");
  await expect(danger).toContainText("1 of 40 danger cases missed");
  await expect(danger).toHaveCSS("background-color", "rgb(198, 40, 40)");
  await expect(page.getByRole("region", { name: "Safety" })).toContainText("high: 1 · medium: 1");

  const evalTable = page.getByRole("table", { name: "Evaluation by category" });
  await expect(evalTable.getByRole("row", { name: /Battery/ })).toContainText("60.0%");
  await expect(evalTable.getByRole("row", { name: /All/ })).toContainText("65.0%");
  await expect(page.getByTestId("no-real-cases")).toBeVisible();

  const confirmed = page.getByRole("table", { name: "Confirmed accuracy by category" });
  await expect(confirmed.getByRole("row", { name: /Battery/ })).toContainText("56.3%");
  await expect(confirmed.getByRole("row", { name: /Brakes/ })).toContainText("Not enough data yet (8 of 30 cases)");
  await expect(page.getByRole("table", { name: "Confirmed accuracy by dataset version" })).toContainText("Version 7");

  const diag = page.getByRole("region", { name: /Diagnoses/ });
  await expect(diag).toContainText("19.6%"); // low confidence
  await expect(diag).toContainText("75.0%"); // helpful
  await expect(diag.getByText("LLM off")).toHaveCount(2); // failures and fallback rate
  await expect(diag).not.toContainText("NaN");

  // Real cases have their own table, never the main one.
  fake.quality.real = { cases: 3, overall: { n: 3, ranked_n: 3, top1: 0.6667, top3: 1 }, skipped: [],
    by_category: [{ category: "battery", name: "Battery", n: 3, ranked_n: 3, top1: 0.6667, top3: 1 }] }; // prettier-ignore
  await page.getByRole("button", { name: "Last 7 days" }).click();
  await expect(page.getByRole("table", { name: "Real cases by category" })).toContainText("66.7%");
  await expect(page.getByRole("table", { name: "Evaluation by category" })).not.toContainText("66.7%");
  expect(fake.quality.qualityQueries.at(-1)).toBe("?days=7");
});

test("review lists open a masked, read-only replay; add a case to the golden set once", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/quality");
  const list = page.getByRole("list", { name: "Review list" });
  await expect(list).toContainText("wrong answer, ring [PHONE]");
  await page.getByRole("tab", { name: "No match" }).click();
  await expect(list).toContainText("No cause found");
  await page.getByRole("tab", { name: "Low confidence" }).click();
  await list.getByRole("link").first().click();

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Session replay");
  const steps = page.getByRole("list", { name: "Session steps" });
  await expect(steps.getByRole("listitem")).toHaveCount(7);
  await expect(steps.getByRole("listitem").nth(3)).toContainText("taken back: did not count");
  await expect(page.locator("main")).not.toContainText(/\d{10}/); // no phone numbers anywhere
  await expect(page.getByRole("textbox")).toHaveCount(0); // read-only
  await expect(page.getByTestId("replay-request")).toContainText("mechanic confirmed Loose battery terminal (F08-BT-02)");

  await page.getByRole("button", { name: "Add to golden set" }).click();
  const dialog = page.getByRole("dialog", { name: "Add to golden set" });
  await expect(dialog.getByLabel("Right fault")).toHaveValue("F08-BT-02"); // the mechanic's confirmed fault
  await expect(dialog.getByLabel("Who confirmed it")).toHaveValue("mechanic");
  await dialog.getByLabel("Right fault").selectOption("");
  await dialog.getByRole("button", { name: "Add case" }).click();
  await expect(dialog.getByText("Choose the right fault, or the safety alert this case should show.")).toBeVisible();
  expect(fake.quality.golden).toHaveLength(0);
  await dialog.getByLabel("Right fault").selectOption("F08-BT-02");
  await dialog.getByLabel("Note (optional)").fill("terminal was loose");
  await dialog.getByRole("button", { name: "Add case" }).click();
  await expect(page.getByTestId("in-golden")).toContainText("In the golden set as platform-abc123def456");
  await expect(page.getByRole("button", { name: "Add to golden set" })).toHaveCount(0);
  expect(fake.quality.golden).toEqual([
    { id: SESSION, body: { expected: ["F08-BT-02"], expected_alert: null, confirmed_by: "mechanic", note: "terminal was loose" } },
  ]);
});

test("permissions: support agents and mechanics have no Quality page or replays", async ({ page, isMobile }) => {
  const fake = await new FakeAdmin().as("agent@im.test").install(page);
  await page.goto("/quality");
  await expect(page.getByTestId("no-access")).toContainText("Your role doesn't include Quality");
  await page.goto(`/quality/sessions/${SESSION}`);
  await expect(page.getByTestId("no-access")).toBeVisible();
  if (isMobile) await page.getByRole("button", { name: "Menu" }).click();
  await expect(page.getByRole("navigation", { name: "Admin" }).locator("visible=true").getByRole("link", { name: "Quality" })).toHaveCount(0);
  expect(fake.quality.qualityQueries).toHaveLength(0);
  fake.as("mech@im.test");
  await page.goto("/quality");
  await expect(page.getByTestId("no-access")).toBeVisible();
});
