import { expect, test } from "@playwright/test";

import { FakeAdmin } from "./fake-admin";

const PNG = { name: "pads.png", mimeType: "image/png", buffer: Buffer.from("89504e470d0a1a0a", "hex") };

test("vehicles: add a generation and change a variant's segment; a variant in use cannot be deleted", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/vehicles");
  await page.getByRole("button", { name: /Maruti Suzuki/ }).click();
  await page.getByRole("button", { name: /^Swift/ }).click();
  const panel = page.getByRole("region", { name: "Maruti Suzuki Swift" });
  await panel.getByRole("button", { name: "Add generation" }).click();
  let dialog = page.getByRole("dialog", { name: "Add generation" });
  await dialog.getByLabel("Name (e.g. 3rd gen)").fill("3rd gen");
  await dialog.getByLabel("First year").fill("2018");
  await dialog.getByLabel(/Last year/).fill("2017");
  await dialog.getByRole("button", { name: "Save generation" }).click();
  await expect(dialog.getByText("The last year is before the first")).toBeVisible();
  await dialog.getByLabel(/Last year/).fill("2023");
  await dialog.getByRole("button", { name: "Save generation" }).click();
  await expect(page.getByText("Saved 3rd gen.")).toBeVisible();

  await panel.getByRole("table").getByRole("button", { name: "Edit" }).click();
  dialog = page.getByRole("dialog", { name: "Edit variant" });
  await dialog.getByLabel("Price segment").selectOption("mid");
  await dialog.getByLabel("automatic engine start-stop").selectOption("no");
  await dialog.getByRole("button", { name: "Save variant" }).click();
  await expect(page.getByText("Saved Swift variant.")).toBeVisible();
  const put = fake.parts.vehicleSaves.find((s) => s.method === "PUT")!;
  expect(put.body).toMatchObject({ price_segment: "mid", features: { start_stop: false }, model_id: 10 });

  await panel.getByRole("table").getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText(/diagnoses or saved cars use this variant/)).toBeVisible();
});

test("parts: a price needs a source and date; ₹20,000+ is flagged and needs another person's second look", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/parts?draft=50");
  await page.getByRole("table", { name: "Parts" }).getByRole("link", { name: "Front brake pads" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Front brake pads");

  // A picture through the photo storage.
  await page.getByRole("region", { name: "Pictures" }).getByLabel("Upload a picture").setInputFiles(PNG);
  await expect(page.getByRole("list", { name: "Part pictures" }).getByRole("listitem")).toHaveCount(1);
  await page.getByRole("button", { name: "Save pictures" }).click();
  await expect(page.getByText("Pictures saved in the draft.")).toBeVisible();
  expect(fake.parts.uploads).toHaveLength(1);

  // A new price without a source is refused by the form; with one, ₹24,000 is flagged.
  await page.getByRole("button", { name: "Add a price" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a price" });
  await dialog.getByLabel("Segment").selectOption("premium");
  await dialog.getByLabel("Price (₹)").fill("24000");
  await expect(dialog.getByTestId("big-price")).toContainText("flagged until a second person checks it");
  await dialog.getByRole("button", { name: "Save price in draft" }).click();
  await expect(dialog.getByText("A price needs its source: the supplier or a link")).toBeVisible();
  expect(fake.parts.saves).toHaveLength(1); // the picture only
  await dialog.getByLabel("Source: supplier").fill("Dealer quote, Okhla");
  await dialog.getByRole("button", { name: "Save price in draft" }).click();
  await expect(page.getByText(/20,000 rupees or more: it is flagged/)).toBeVisible();

  // The person who entered it cannot give it the second look.
  await page.goto("/parts?tab=prices&draft=50");
  const prices = page.getByRole("table", { name: "Prices" });
  await prices.getByRole("row", { name: /24,000/ }).getByRole("button", { name: "Second look" }).click();
  await expect(page.getByText("A second person must check this price: you entered it.")).toBeVisible();
  fake.as("boss@im.test");
  await page.reload();
  await prices.getByRole("row", { name: /24,000/ }).getByRole("button", { name: "Second look" }).click();
  await expect(prices.getByRole("row", { name: /24,000/ })).toContainText("checked by boss@im.test");
});

test("labour: fill a zone rate with its source and date; import a CSV after checking it", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/parts?tab=labour&draft=50");
  await page.getByRole("button", { name: "Edit Gurugram budget rate" }).click();
  const dialog = page.getByRole("dialog", { name: "Gurugram: budget cars" });
  await dialog.getByLabel("Per hour from (₹)").fill("500");
  await dialog.getByLabel("Per hour up to (₹)").fill("700");
  await dialog.getByRole("button", { name: "Save in draft" }).click();
  await expect(dialog.getByText("The source needs at least 3 characters")).toBeVisible();
  await dialog.getByLabel(/Source/).fill("5 garages, Sector 14-56, phone survey");
  await dialog.getByRole("button", { name: "Save in draft" }).click();
  await expect(page.getByText("Saved Gurugram budget.")).toBeVisible();
  expect(fake.parts.saves.at(-1)).toMatchObject({ entity: "zone_rate", key: "gurugram|budget", data: { rate_min_inr: 500, rate_max_inr: 700 } });
  await expect(page.getByRole("link", { name: /Download as zone_labour_rates.yaml/ })).toHaveAttribute("href", /zone-rates\.yaml$/);

  await page.getByRole("tab", { name: "Import CSV" }).click();
  const csv = "part_type,description,brand,part_number,quantity,segment,price_inr,price_max_inr,supplier,source_url,checked_on\n" +
    "Brake pad set,Front pads,Bosch,P1,1,budget,1450,,Boodmo,,2026-10-30\nWiper,Wiper blade,,,1,budget,300,,Amazon,,\n";
  await page.getByLabel("CSV file", { exact: true }).setInputFiles({ name: "prices.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Check the file" }).click();
  const preview = page.getByTestId("import-preview");
  await expect(preview).toContainText("2 rows · 1 valid · 1 with errors");
  await expect(preview).toContainText("checked_on: Field required");
  await page.getByRole("button", { name: "Import 1 valid rows into draft v50" }).click();
  await expect(page.getByText("Imported 1 rows into draft v50.")).toBeVisible();
  expect(fake.parts.imports).toEqual([false, true]);
});

test("sign-off: bulk sign-off of the filtered items in one go", async ({ page }) => {
  const fake = await new FakeAdmin().as("content@im.test").install(page);
  await page.goto("/knowledge?tab=signoff&draft=50");
  await page.getByLabel("Type").selectOption("question");
  await page.getByRole("button", { name: "Sign off all 1 shown" }).click();
  const dialog = page.getByRole("dialog", { name: "Sign off 1 items?" });
  await expect(dialog).toContainText("one entry with the count and the filter");
  await dialog.getByRole("button", { name: "Sign off 1" }).click();
  await expect(page.getByText("Signed off 1 items.")).toBeVisible();
  expect(fake.parts.bulk[0]).toMatchObject({ items: [{ entity: "question", key: "battery/battery-main" }], filter: { pending_only: true, entity: "question" } });
});

test("permissions: a support agent sees neither Vehicles nor Parts & Prices", async ({ page }) => {
  await new FakeAdmin().as("agent@im.test").install(page);
  for (const path of ["/vehicles", "/parts", "/parts/PN%3Abosch%3APAD1%3A1"]) {
    await page.goto(path);
    await expect(page.getByTestId("no-access")).toBeVisible();
  }
});
