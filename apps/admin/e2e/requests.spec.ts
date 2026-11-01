import { expect, type Page, test } from "@playwright/test";

import { FakeAdmin } from "./fake-admin";

const refs = (page: Page) => page.getByTestId("queue-row").getByRole("link");
const idOf = (fake: FakeAdmin, ref: string) => fake.ops.requests.find((r) => r.reference === ref)!.id;
const status = (page: Page) => page.getByTestId("request-status");

test("queue: safety-critical first, then urgent, then the oldest; filters and search; phones masked", async ({ page }) => {
  const fake = await new FakeAdmin().as("agent@im.test").install(page);
  await page.goto("/requests");
  await expect(refs(page)).toHaveText(["IM-SAFE03", "IM-WORK04", "IM-URG002", "IM-OLD001"]);
  const first = page.getByTestId("queue-row").first();
  await expect(first).toContainText("Safety-critical");
  await expect(page.getByTestId("queue-row").nth(2)).toContainText("Urgent");
  await expect(page.getByRole("table", { name: "Request queue" })).not.toContainText("+91");
  await expect(first).toContainText("******1234");

  await page.getByLabel("Safety").selectOption("high");
  await expect(refs(page)).toHaveText(["IM-SAFE03"]);
  await expect(page).toHaveURL(/safety=high/);
  expect(fake.ops.queueQueries.at(-1)).toContain("safety=high");
  await page.getByLabel("Safety").selectOption("");

  await page.getByLabel("Category").selectOption("brakes");
  await expect(refs(page)).toHaveText(["IM-SAFE03"]);
  await page.getByLabel("Category").selectOption("");

  await page.getByRole("searchbox").fill("usha");
  await page.getByRole("button", { name: "Search requests" }).click();
  await expect(refs(page)).toHaveText(["IM-URG002"]);
  await page.getByRole("searchbox").fill("");
  await page.getByRole("button", { name: "Search requests" }).click();

  // Controlled by the address: it shows checked once the filtered queue loads.
  await page.getByRole("checkbox", { name: "Only mine" }).click();
  await expect(page.getByRole("checkbox", { name: "Only mine" })).toBeChecked();
  await expect(refs(page)).toHaveText(["IM-SAFE03", "IM-WORK04"]);
  await page.getByRole("checkbox", { name: "Only mine" }).click();
  await expect(page.getByRole("checkbox", { name: "Only mine" })).not.toBeChecked();

  await page.getByRole("button", { name: "Closed" }).click();
  await expect(refs(page)).toHaveText(["IM-DONE05"]);
  await page.reload(); // the filters live in the address
  await expect(refs(page)).toHaveText(["IM-DONE05"]);
  await expect(page.getByRole("button", { name: "Closed" })).toHaveAttribute("aria-pressed", "true");
});

test("assign: rough location, reveal the owner's number, offer, decline, offer anyway with a note, accept, on to repair", async ({ page }) => {
  const fake = await new FakeAdmin().as("agent@im.test").install(page);
  await page.goto("/requests");
  await page.getByRole("link", { name: "IM-SAFE03" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("IM-SAFE03");
  await expect(page.getByRole("note")).toContainText("Safety-critical");
  await expect(page.getByTestId("rough-location")).toHaveText("rough location");
  await expect(page.getByText("only has a rough location")).toBeVisible(); // the matching note
  // Leaflet drew the request and the suggested mechanic's base (tiles are blocked in tests).
  const map = page.getByRole("region", { name: "Where IM-SAFE03 is" });
  await expect(map).toHaveClass(/leaflet-container/);
  await expect(map.locator("path.leaflet-interactive")).toHaveCount(2);

  // The owner reveals the number (audited by the API).
  await expect(page.getByTestId("masked-phone")).toHaveText("******1234");
  await page.getByRole("button", { name: "Show number" }).click();
  await expect(page.getByRole("link", { name: "+919800001234" })).toHaveAttribute("href", "tel:+919800001234");
  expect(fake.ops.reveals).toEqual(["IM-SAFE03"]);

  // Suggestions with reasons; offer to the first, who declines.
  const suggested = page.getByRole("list", { name: "Suggested mechanics" });
  await expect(suggested.getByRole("listitem").filter({ hasText: "Ravi Kumar" })).toContainText("km away");
  await page.getByRole("button", { name: "Offer job to Ravi Kumar" }).click();
  await expect(status(page)).toHaveText("Offered to a mechanic");
  await expect(page.getByTestId("open-assignment")).toContainText("Ravi Kumar was offered the job");
  await page.getByRole("button", { name: "Mechanic declined" }).click();
  await expect(status(page)).toHaveText("Triaged");

  // Someone who is not a suggestion needs a note saying why.
  await page.getByText("Left out (2)").click();
  await page.getByRole("button", { name: "Offer anyway to Sunita Devi" }).click();
  const dialog = page.getByRole("dialog", { name: "Offer to Sunita Devi anyway?" });
  await dialog.getByRole("button", { name: "Offer job" }).click();
  await expect(dialog.getByText("Write a short note.")).toBeVisible();
  await dialog.getByLabel("Why").fill("Ravi declined; Sunita knows brakes too");
  await dialog.getByRole("button", { name: "Offer job" }).click();
  await expect(dialog).toBeHidden();
  expect(fake.ops.offers).toEqual([
    { mechanic_id: 1, note: "" },
    { mechanic_id: 2, note: "Ravi declined; Sunita knows brakes too" },
  ]);
  await page.getByRole("button", { name: "Mechanic accepted" }).click();
  await expect(status(page)).toHaveText("Mechanic accepted");

  await page.getByRole("button", { name: "Mechanic is on the way" }).click();
  await expect(status(page)).toHaveText("Mechanic on the way");
  await page.getByRole("button", { name: "Mechanic arrived" }).click();
  await expect(status(page)).toHaveText("Mechanic arrived");
  await page.getByRole("button", { name: "Repair started" }).click();
  await expect(status(page)).toHaveText("Repair in progress");
  await expect(page.getByRole("heading", { name: "Complete the job" })).toBeVisible();

  const timeline = page.getByRole("list", { name: "Timeline" });
  await expect(timeline).toContainText("Ravi Kumar declined");
  await expect(timeline).toContainText("Sunita Devi accepted");
  await expect(timeline.getByRole("listitem").first()).toContainText("Mechanic arrived → Repair in progress");
});

test("ownership and notes: take a request to see the number; cancelling needs a reason", async ({ page }) => {
  const fake = await new FakeAdmin().as("agent@im.test").install(page);
  await page.goto(`/requests/${idOf(fake, "IM-OLD001")}`);
  await expect(page.getByText("Only the agent who owns this request can see the full number.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Show number" })).toHaveCount(0);
  await page.getByRole("button", { name: "Take this request" }).click();
  await expect(page.getByText("Owner: Agent (you)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Show number" })).toBeVisible();

  await page.getByLabel("Add a note").fill("Called twice, no answer");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByRole("list", { name: "Internal notes" })).toContainText("Called twice, no answer");

  await page.getByRole("button", { name: "Cancel request" }).click();
  const dialog = page.getByRole("dialog", { name: "Cancel this request?" });
  await dialog.getByRole("button", { name: "Cancel request" }).click();
  await expect(dialog.getByText("Write a short note.")).toBeVisible();
  await dialog.getByLabel("Why").fill("Customer fixed it themselves");
  await dialog.getByRole("button", { name: "Cancel request" }).click();
  await expect(status(page)).toHaveText("Cancelled");
  await expect(page.getByRole("button", { name: "Take this request" })).toHaveCount(0); // closed: no actions
});

test("complete-job form: the fault is required, other needs a description, parts and cost are sent", async ({ page }) => {
  const fake = await new FakeAdmin().as("agent@im.test").install(page);
  await page.goto(`/requests/${idOf(fake, "IM-WORK04")}`);
  const form = page.getByRole("form", { name: "Complete the job" });
  await expect(form.getByLabel("Confirmed fault")).toContainText("AI #1: Weak battery (F08-BT-01)");

  await form.getByRole("button", { name: "Complete job" }).click();
  await expect(form.getByText("Choose the fault the mechanic found, or Other.")).toBeVisible();
  await form.getByLabel("Confirmed fault").selectOption({ label: "Other (describe it)" });
  await form.getByRole("button", { name: "Complete job" }).click();
  await expect(form.getByText("Say what the fault was.")).toBeVisible();
  expect(fake.ops.outcomes).toHaveLength(0);

  await form.getByLabel("Confirmed fault").selectOption({ label: "AI #1: Weak battery (F08-BT-01)" });
  await form.getByRole("button", { name: "Add a part" }).click();
  await form.getByRole("button", { name: "Complete job" }).click();
  await expect(form.getByText("Give the part's name, or remove the row.")).toBeVisible();
  await form.getByLabel("Part 1", { exact: true }).fill("Battery 35Ah");
  await form.getByLabel("Part 1 price (₹)").fill("3800");
  await form.getByLabel("Final cost (₹)").fill("4200");
  await form.getByLabel("Mechanic's notes").fill("Battery was dead, replaced");
  await form.getByRole("button", { name: "Complete job" }).click();

  await expect(status(page)).toHaveText("Completed");
  await expect(form).toBeHidden();
  const outcome = page.getByRole("region", { name: "Outcome" });
  await expect(outcome).toContainText("Weak battery (F08-BT-01)");
  await expect(outcome).toContainText("The AI's top cause");
  await expect(outcome).toContainText("1 × Battery 35Ah (₹3,800)");
  expect(fake.ops.outcomes).toEqual([
    {
      confirmed_fault_key: "F08-BT-01",
      other_text: "",
      parts_used: [{ name: "Battery 35Ah", quantity: 1, price_inr: 3800 }],
      final_cost_inr: 4200,
      mechanic_notes: "Battery was dead, replaced",
    },
  ]);
});

test("permissions: a support agent works requests and mechanics; a content admin and a mechanic cannot", async ({ page, isMobile }) => {
  const fake = await new FakeAdmin().as("agent@im.test").install(page);
  await page.goto("/requests");
  await expect(refs(page).first()).toBeVisible();
  await page.goto("/mechanics/1");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ravi Kumar");
  await expect(page.getByRole("button", { name: "Save zones" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Documents" })).toHaveCount(0); // super admins only

  fake.as("content@im.test");
  await page.goto("/requests");
  await expect(page.getByTestId("no-access")).toContainText("Your role doesn't include Requests");
  await page.goto("/mechanics");
  await expect(page.getByTestId("no-access")).toContainText("Your role doesn't include Mechanics");
  if (isMobile) await page.getByRole("button", { name: "Menu" }).click();
  const nav = page.getByRole("navigation", { name: "Admin" }).locator("visible=true");
  await expect(nav.getByRole("link", { name: "Requests" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Mechanics" })).toHaveCount(0);
  expect(fake.ops.queueQueries).toHaveLength(1); // the content admin's pages never asked the API

  // A mechanic account reads requests only: no actions, no number, no mechanics page.
  fake.as("mech@im.test");
  await page.goto(`/requests/${idOf(fake, "IM-SAFE03")}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("IM-SAFE03");
  await expect(page.getByRole("list", { name: "Suggested mechanics" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Offer job|Show number|Mark|Escalate|Take/ })).toHaveCount(0);
  await page.goto("/mechanics");
  await expect(page.getByTestId("no-access")).toBeVisible();
});
