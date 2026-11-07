import { expect, test } from "@playwright/test";

import { FakeAdmin } from "./fake-admin";

const XLSX = { name: "BATTERY v2.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("PK\u0003\u0004 fake") };

test("datasets: upload, job progress, validation and diff, eval, a blocked publish, then a super admin's override", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/datasets");
  await expect(page.getByRole("heading", { name: "Datasets", level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Live version" })).toContainText("v41 · battery");

  // Upload a battery file: a build job with progress, then a validated draft.
  const form = page.getByRole("form", { name: "Upload a category file" });
  await form.getByRole("button", { name: "Upload and build draft" }).click();
  await expect(form.getByRole("alert")).toHaveText("Choose the category this file is for.");
  await form.getByLabel("Category").selectOption("battery");
  await expect(page.getByTestId("upload-note")).toContainText("file 8 (now BATTERY v1.xlsx)");
  await form.getByLabel("Excel file (.xlsx)").setInputFiles(XLSX);
  await form.getByRole("button", { name: "Upload and build draft" }).click();
  const progress = page.getByTestId("job-progress");
  await expect(progress.getByRole("progressbar", { name: "Building the draft" })).toHaveAttribute("aria-valuenow", "45");
  await expect(progress).toContainText("parts build");
  await expect(progress).toContainText("Done");
  const drafts = page.getByRole("table", { name: "Drafts, newest first" });
  await expect(drafts.getByRole("row", { name: /v42 · battery/ })).toContainText("Validated");

  // The draft: checks, diff, eval.
  await drafts.getByRole("link", { name: "v42 · battery" }).click();
  await expect(page.getByRole("heading", { name: /v42 · battery/, level: 1 })).toBeVisible();
  await expect(page.getByText("search model original MiniLM")).toBeVisible();
  await expect(page.getByTestId("check-nothing_lost")).toContainText("Passed");
  await expect(page.getByTestId("diff-counts")).toContainText("1 added · 1 changed · 1 removed");
  await page.locator("summary", { hasText: /^name$/ }).click();
  await expect(page.getByText("Before: Weak battery")).toBeVisible();
  await expect(page.getByTestId("publish-blockers")).toContainText("Run the evaluation on this draft first.");

  await page.getByRole("button", { name: "Run the evaluation" }).click();
  await expect(page.getByTestId("gate")).toContainText("Publishing is blocked by the eval gate", { timeout: 10_000 });
  await expect(page.getByTestId("gate")).toContainText("Top-3 accuracy drops 5.00 points");
  const results = page.getByTestId("eval-results").first();
  await expect(results.getByRole("row", { name: /Top-3 accuracy/ })).toContainText("80.00%75.00%-5.00");
  await expect(page.getByTestId("override-needed")).toContainText("Only a super admin");
  await expect(page.getByRole("button", { name: /^Publish v42/ })).toHaveCount(0);

  // A super admin overrides with a written reason.
  fake.as("boss@im.test");
  await page.reload();
  const override = page.getByTestId("override");
  const button = override.getByRole("button", { name: "Override the gate and publish" });
  await expect(button).toBeDisabled();
  await override.getByLabel(/Why publish although the gate blocks it/).fill("Two retired faults; mechanic checked it.");
  await button.click();
  await expect(page.getByRole("heading", { name: /v42 · battery/, level: 1 })).toContainText("Live", { timeout: 10_000 });
  await expect(page.getByText("Published over a blocked eval.")).toBeVisible();
  // The steps of the publish run are shown (open), apart from the build's (before later edits).
  await expect(page.getByTestId("steps-published")).toContainText("2 edits applied");
  await expect(page.getByTestId("steps-built")).toContainText("Steps that ran when the draft was built");
  expect(fake.datasets.publishBodies.at(-1)).toEqual({ override_reason: "Two retired faults; mechanic checked it." });
});

test("datasets: roll a category back to an archived version in one click", async ({ page }) => {
  const fake = await new FakeAdmin().as("boss@im.test").install(page);
  await page.goto("/datasets/40");
  await expect(page.getByRole("heading", { name: /v40 · import of every file/, level: 1 })).toContainText("Archived");
  const card = page.getByRole("region", { name: "Roll back" });
  await card.getByLabel("Category to roll back").selectOption("battery");
  await card.getByRole("button", { name: "Roll back Battery dead / weak to v40" }).click();
  const dialog = page.getByRole("dialog", { name: "Roll back Battery dead / weak to v40?" });
  await dialog.getByRole("button", { name: "Roll back" }).click();
  await expect(page.getByTestId("job-progress")).toContainText("Rolling back");
  await expect.poll(() => fake.datasets.versions.find((v) => v.status === "published")?.id, { timeout: 10_000 }).toBe(42);
  expect(fake.datasets.rollbackBodies).toEqual([{ category: "battery" }]);
  await page.goto("/datasets");
  await expect(page.getByText("v42 · battery rolled back to v40").first()).toBeVisible();
});

test("datasets: the free demo says dataset changes are switched off and offers no upload", async ({ page }) => {
  const fake = new FakeAdmin().as("content@im.test");
  fake.datasets.jobsEnabled = false;
  await fake.install(page);
  await page.goto("/datasets");
  await expect(page.getByTestId("jobs-off")).toContainText("Dataset changes are switched off on this server");
  await expect(page.getByRole("region", { name: "Live version" })).toContainText("v41 · battery");
  await expect(page.getByRole("form", { name: "Upload a category file" })).toHaveCount(0);
});
