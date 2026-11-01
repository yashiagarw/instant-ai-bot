import { expect, test } from "@playwright/test";

import { FakeAdmin } from "./fake-admin";

const PDF = { name: "aadhaar.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 test") };

test("mechanics: list with duty switch; add one; skills, zones (rough pincode) and shifts", async ({ page }) => {
  const fake = await new FakeAdmin().as("agent@im.test").install(page);
  await page.goto("/mechanics");
  const table = page.getByRole("table", { name: "Mechanics" });
  await expect(table.getByRole("row", { name: /Sunita Devi/ })).toContainText("(rough location)");
  const duty = page.getByRole("switch", { name: "On duty: Mohan Lal" });
  await expect(duty).toHaveAttribute("aria-checked", "false");
  await duty.click();
  await expect(duty).toHaveAttribute("aria-checked", "true");
  expect(fake.ops.mechanics.find((m) => m.name === "Mohan Lal")!.on_duty).toBe(true);

  await page.getByRole("button", { name: "Add mechanic" }).click();
  const dialog = page.getByRole("dialog", { name: "Add mechanic" });
  await dialog.getByLabel("Name").fill("Imran Khan");
  await dialog.getByLabel("Mobile number").fill("12345");
  await dialog.getByLabel("Base pincode").fill("110017");
  await dialog.getByRole("button", { name: "Save mechanic" }).click();
  await expect(dialog.getByText("A 10-digit Indian mobile number")).toBeVisible();
  await dialog.getByLabel("Mobile number").fill("98100 12345");
  await dialog.getByRole("button", { name: "Save mechanic" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Imran Khan");
  await expect(page.getByText("Mechanic added.")).toBeVisible();

  const skills = page.getByRole("region", { name: "Skills" });
  await skills.getByRole("checkbox", { name: "Battery" }).check();
  await skills.getByRole("button", { name: "Save skills" }).click();
  await expect(skills.getByText("Skills saved (1).")).toBeVisible();

  const zones = page.getByRole("region", { name: "Zones" });
  await zones.getByRole("textbox", { name: "Pincode", exact: true }).fill("1100");
  await zones.getByRole("button", { name: "Add pincode" }).click();
  await expect(zones.getByText("A pincode has 6 digits.")).toBeVisible();
  await zones.getByRole("textbox", { name: "Pincode", exact: true }).fill("110004");
  await zones.getByRole("button", { name: "Add pincode" }).click();
  await zones.getByLabel("Radius (km)").fill("8");
  await zones.getByRole("button", { name: "Add radius" }).click();
  await zones.getByRole("button", { name: "Save zones" }).click();
  await expect(zones.getByText("Zones saved (3).")).toBeVisible();
  const list = zones.getByRole("list", { name: "Zones" });
  await expect(list.getByRole("listitem").filter({ hasText: "Pincode 110004" })).toContainText("(rough location)");
  await expect(list).toContainText("8 km around the base");

  const shifts = page.getByRole("region", { name: "Weekly shifts" });
  await shifts.getByRole("button", { name: "Add Monday shift" }).click();
  await shifts.getByRole("button", { name: "Add Monday shift" }).click();
  await shifts.getByRole("button", { name: "Save shifts" }).click();
  await expect(shifts.getByText("Monday: two shifts overlap.")).toBeVisible();
  await shifts.getByLabel("Monday shift 1 ends").fill("13:00");
  await shifts.getByLabel("Monday shift 2 starts").fill("14:00");
  await shifts.getByRole("button", { name: "Save shifts" }).click();
  await expect(shifts.getByText("Shifts saved (2).")).toBeVisible();
  expect(fake.ops.mechanics.at(-1)!.shifts).toEqual([
    { weekday: 0, start_time: "09:00", end_time: "13:00" },
    { weekday: 0, start_time: "14:00", end_time: "18:00" },
  ]);
});

test("documents: super admins upload, see and delete them", async ({ page }) => {
  const fake = await new FakeAdmin().as("boss@im.test").install(page);
  await page.goto("/mechanics/1");
  const docs = page.getByRole("region", { name: "Documents" });
  await expect(docs.getByText("No documents.")).toBeVisible();
  await docs.getByLabel("Kind").selectOption("driving_licence");
  await docs.getByLabel(/^File/).setInputFiles(PDF);
  await docs.getByRole("button", { name: "Upload document" }).click();
  await expect(docs.getByText("aadhaar.pdf stored (encrypted).")).toBeVisible();
  await expect(docs.getByRole("link", { name: "View aadhaar.pdf" })).toHaveAttribute("href", /\/api\/admin\/mechanics\/1\/documents\/1$/);
  expect(fake.ops.documents[0]).toMatchObject({ kind: "driving_licence", filename: "aadhaar.pdf" });

  await docs.getByRole("button", { name: "Delete aadhaar.pdf" }).click();
  await page.getByRole("dialog", { name: "Delete this document?" }).getByRole("button", { name: "Delete document" }).click();
  await expect(docs.getByText("aadhaar.pdf deleted.")).toBeVisible();
  expect(fake.ops.documents).toHaveLength(0);
});
