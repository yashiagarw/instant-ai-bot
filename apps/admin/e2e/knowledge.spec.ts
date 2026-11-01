import { expect, test } from "@playwright/test";

import { FakeAdmin } from "./fake-admin";

test("knowledge: edit a fault, its symptoms and a Hindi synonym in the draft; the changes list them and can revert", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/knowledge");
  await expect(page.getByRole("region", { name: "Draft being edited" })).toContainText("Editing draft v50");
  await page.getByRole("table", { name: "Faults" }).getByRole("link", { name: "F08-BT-01" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Weak battery");

  // Details: an empty name is refused by the form (Zod) before anything is sent.
  const details = page.getByRole("region", { name: "Details" });
  await details.getByLabel("Name").fill("");
  await details.getByRole("button", { name: "Save details" }).click();
  await expect(details.getByText("The name needs at least 2 characters")).toBeVisible();
  expect(fake.knowledge.saves).toHaveLength(0);
  await details.getByLabel("Name").fill("Weak or dead battery");
  await details.getByLabel(/Weight/).fill("2.5");
  await details.getByRole("button", { name: "Add a requirement" }).click();
  await details.getByLabel("Requirement 1", { exact: true }).selectOption("fuel");
  await details.getByLabel("Value", { exact: true }).fill("petrol, diesel");
  await details.getByRole("button", { name: "Save details" }).click();
  await expect(details.getByText("Saved in the draft.")).toBeVisible();
  expect(fake.knowledge.saves.at(-1)).toMatchObject({ entity: "fault", key: "F08-BT-01",
    data: { name: "Weak or dead battery", prior: 2.5, requires: [{ fuel: ["petrol", "diesel"] }] } }); // prettier-ignore

  // Symptoms: add a line.
  const symptoms = page.getByRole("form", { name: "Symptoms" });
  await symptoms.getByRole("button", { name: "Add a line" }).click();
  await symptoms.getByLabel("Symptoms 3").fill("Battery light on the dashboard");
  await symptoms.getByRole("button", { name: "Save symptoms" }).click();
  await expect(page.getByRole("region", { name: /^Symptoms/ }).getByText("Saved in the draft.")).toBeVisible();
  expect(fake.knowledge.saves.at(-1)).toMatchObject({ entity: "fault_items", key: "F08-BT-01/symptom",
    data: { lines: ["Clicking sound", "Dim lights", "Battery light on the dashboard"] } }); // prettier-ignore

  // A Hindi (Devanagari) synonym; a held-out phrase cannot be deleted.
  const add = page.getByRole("form", { name: "Add a phrase" });
  await add.getByLabel("New phrase").fill("गाड़ी स्टार्ट नहीं हो रही");
  await add.getByLabel("Language").selectOption("hi");
  await add.getByLabel("English meaning").fill("the car will not start");
  await add.getByRole("button", { name: "Add phrase" }).click();
  await expect(page.getByRole("list", { name: "Phrases" })).toContainText("गाड़ी स्टार्ट नहीं हो रही");
  await expect(page.getByRole("button", { name: "Delete phrase battery down hai" })).toHaveCount(0);

  // The Changes tab lists the edits; revert one.
  await page.goto("/knowledge?tab=changes&draft=50");
  const summary = page.getByTestId("editor-summary");
  await expect(summary.getByRole("row", { name: /^fault / })).toContainText("1");
  const edits = page.getByRole("list", { name: "Edits in this draft" });
  await expect(edits.getByRole("listitem")).toHaveCount(3);
  await edits.getByRole("listitem").filter({ hasText: "fault F08-BT-01" }).getByRole("button", { name: "Revert" }).click();
  await expect(edits.getByRole("listitem")).toHaveCount(2);
  expect((fake.knowledge.items["fault:F08-BT-01"] as { name: string }).name).toBe("Weak battery");
});

test("knowledge: a safety rule change warns and needs confirmation; sign-off under your name; question effects", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/knowledge?tab=safety&draft=50");
  await page.getByRole("table", { name: "Safety rules" }).getByRole("button", { name: "Edit" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("safety-warning")).toContainText("You are changing a safety rule");
  await dialog.getByLabel("What to do at the roadside").fill("Park away from people. Do not charge it.");
  await dialog.getByRole("button", { name: "Save safety rule in draft" }).click();
  await expect(dialog.getByText("Confirm that you checked this safety change")).toBeVisible();
  expect(fake.knowledge.saves).toHaveLength(0);
  await dialog.getByLabel("I checked this safety change").check();
  await dialog.getByRole("button", { name: "Save safety rule in draft" }).click();
  await expect(dialog).toBeHidden();
  expect(fake.knowledge.saves.at(-1)).toMatchObject({ entity: "safety_rule", data: { roadside_action: "Park away from people. Do not charge it." } });

  // Sign-off tab: pending filter, sign off as me.
  await page.getByRole("tab", { name: "Sign-off" }).click();
  const table = page.getByRole("table", { name: "Items for sign-off" });
  await expect(table.getByRole("row")).toHaveCount(3); // header + 2 pending
  await table.getByRole("row", { name: /What problem are you facing/ }).getByRole("button", { name: "Sign off as me" }).click();
  await expect(page.getByText("Signed off: What problem are you facing?")).toBeVisible();
  await expect(table.getByRole("row")).toHaveCount(2);
  expect((fake.knowledge.items["question:battery/battery-main"] as { reviewed_by: string }).reviewed_by).toBe("content@im.test");

  // Questions: change an effect's strength.
  await page.getByRole("tab", { name: "Questions" }).click();
  await page.getByLabel("Category").selectOption("battery");
  await page.getByRole("button", { name: "Edit question" }).click();
  const q = page.getByRole("dialog", { name: "Edit question" });
  await q.getByLabel("Strength").first().selectOption("weak");
  await q.getByRole("button", { name: "Save question in draft" }).click();
  await expect(q).toBeHidden();
  const saved = fake.knowledge.saves.at(-1) as { data: { options: { effects: { strength: string }[] }[] } };
  expect(saved.data.options[0].effects[0].strength).toBe("weak");
  await expect(page.getByRole("list", { name: "Questions" })).toContainText("+F08-BT-01 (weak)");

  // The publish summary lists the safety change by name.
  await page.getByRole("tab", { name: "Changes in this draft" }).click();
  await expect(page.getByTestId("safety-changes")).toContainText("safety rule F08-BT-03/sheet/general");
  await expect(page.getByTestId("safety-changes")).toContainText("Do not charge it → Park away from people. Do not charge it.");
});

test("review queues: unlisted cars are added to the catalogue or dismissed", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/vehicles");
  const table = page.getByRole("table", { name: "Unlisted cars waiting for review" });
  await expect(table).toContainText("tata curvv 2025");
  await table.getByRole("button", { name: "Add to catalogue" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("First year").fill("2024");
  await dialog.getByLabel("dct").check();
  await dialog.getByRole("button", { name: "Add to catalogue" }).click();
  await expect(page.getByText("Added: model Tata Curvv")).toBeVisible();
  expect(fake.knowledge.added[0]).toMatchObject({ make: "Tata", model: "Curvv", year_from: 2024, fuel: "petrol", price_segment: "mid",
    transmissions: ["mt", "dct"] }); // prettier-ignore
  await page.goto("/knowledge/review");
  await expect(page.getByRole("heading", { name: /Questions waiting for sign-off \(1\)/ })).toBeVisible();
});

test("permissions: a support agent has no Knowledge or Vehicles; a mechanic neither", async ({ page }) => {
  for (const who of ["agent@im.test", "mech@im.test"]) {
    await new FakeAdmin().as(who).install(page);
    for (const path of ["/knowledge", "/knowledge/faults/F08-BT-01", "/knowledge/review", "/vehicles"]) {
      await page.goto(path);
      await expect(page.getByTestId("no-access")).toBeVisible();
    }
    await page.unrouteAll({ behavior: "ignoreErrors" });
  }
});
