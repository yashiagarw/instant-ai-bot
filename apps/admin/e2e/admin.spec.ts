import { expect, type Page, test } from "@playwright/test";

import { FakeAdmin, PASSWORD, SETUP_KEY } from "./fake-admin";

const ALL = ["Overview", "Requests", "Mechanics", "Auto-offer", "Knowledge", "Vehicles", "Parts & Prices", "Datasets", "Quality", "Users", "Audit log"];
const MENUS: Record<string, string[]> = {
  "boss@im.test": ALL,
  "content@im.test": ["Overview", "Knowledge", "Vehicles", "Parts & Prices", "Datasets", "Quality"],
  "agent@im.test": ["Overview", "Requests", "Mechanics", "Users"],
  "mech@im.test": ["Overview", "Requests"],
};

/** The menu links (on phones the menu opens from the header first). */
async function menu(page: Page, isMobile: boolean) {
  if (isMobile) await page.getByRole("button", { name: "Menu" }).click();
  return page.getByRole("navigation", { name: "Admin" }).locator("visible=true");
}

async function signIn(page: Page, email: string, code = "123456") {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel(/6-digit code/).fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("login: password, then the two-factor code; a wrong code is explained; back to the page asked for", async ({ page }) => {
  await new FakeAdmin().install(page);
  await page.goto("/audit");
  await expect(page).toHaveURL(/\/login\?next=%2Faudit$/);
  await expect(page.getByRole("heading", { name: "Staff sign in" })).toBeVisible();

  await page.getByLabel("Email").fill("boss@im.test");
  await page.getByLabel("Password").fill("wrong password");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.locator("form").getByRole("alert")).toHaveText("Email, password or code is wrong.");

  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Two-factor code" })).toBeVisible();
  await page.getByLabel(/6-digit code/).fill("000000");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator("form").getByRole("alert")).toHaveText("Email, password or code is wrong.");
  await page.getByLabel(/6-digit code/).fill("123456");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/audit$/);
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
});

test("an account without two-factor sees the QR code and key once, then a code signs it in", async ({ page, isMobile }) => {
  const fake = await new FakeAdmin().install(page);
  await page.goto("/login");
  await page.getByLabel("Email").fill("new@im.test");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Continue" }).click();

  const setup = page.getByTestId("two-factor-setup");
  await expect(setup.getByRole("heading", { name: "Set up two-factor" })).toBeVisible();
  await expect(setup.getByRole("img", { name: /QR code/ })).toBeVisible();
  await expect(setup.getByTestId("setup-key")).toHaveText("JBSW Y3DP EHPK 3PXP JBSW Y3DP");
  await expect(setup.getByText("This QR code and key are shown only now.")).toBeVisible();
  await setup.getByLabel(/6-digit code/).fill("111111");
  await setup.getByRole("button", { name: "Finish and sign in" }).click();
  await expect(setup.getByRole("alert")).toContainText("doesn't match");
  await setup.getByLabel(/6-digit code/).fill("654321");
  await setup.getByRole("button", { name: "Finish and sign in" }).click();

  // Invited with a temporary password: only the password form until they choose their own.
  await expect(page.getByRole("heading", { name: "Choose your own password" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Admin" })).toHaveCount(0);
  await page.getByLabel("Current password").fill(PASSWORD);
  await page.getByLabel(/Code from your authenticator/).fill("123456");
  await page.getByLabel("New password", { exact: true }).fill("my very own passphrase 9");
  await page.getByLabel("New password again").fill("my very own passphrase 9");
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();

  // Next time: the code, never the QR code again.
  if (isMobile) await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("button", { name: "Sign out" }).locator("visible=true").click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email").fill("new@im.test");
  await page.getByLabel("Password").fill("my very own passphrase 9");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Two-factor code" })).toBeVisible();
  await expect(page.getByText(SETUP_KEY.slice(0, 4))).toHaveCount(0);
  expect(fake.accounts.find((a) => a.email === "new@im.test")!.two_factor).toBe(true);
});

for (const [email, expected] of Object.entries(MENUS)) {
  test(`menu items by role: ${email.split("@")[0]}`, async ({ page, isMobile }) => {
    await new FakeAdmin().install(page);
    await page.goto("/login");
    await signIn(page, email);
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
    const nav = await menu(page, isMobile);
    await expect(nav.getByRole("link")).toHaveText(expected);
    // Pages behind hidden items say "No access" when opened by their address.
    for (const label of ALL.filter((l) => !expected.includes(l))) {
      const href = { "Parts & Prices": "/parts", "Audit log": "/audit", "Auto-offer": "/dispatch" }[label] ?? `/${label.toLowerCase()}`;
      await page.goto(href);
      await expect(page.getByTestId("no-access")).toBeVisible();
    }
  });
}

test("users: invite staff (temporary password once), filter by role, customers masked with an audited reveal", async ({ page }) => {
  const fake = await new FakeAdmin().as("boss@im.test").install(page);
  await page.goto("/users");
  const table = page.getByRole("table", { name: "Staff accounts" });
  await expect(table.getByRole("row")).toHaveCount(1 + 5);
  await page.getByRole("combobox", { name: "Role" }).selectOption("mechanic");
  await expect(table.getByRole("row")).toHaveCount(1 + 2);
  await page.getByRole("combobox", { name: "Role" }).selectOption("");
  await page.getByRole("searchbox", { name: "Search staff" }).fill("agent@im");
  await expect(table.getByRole("row")).toHaveCount(1 + 1);
  await page.getByRole("searchbox", { name: "Search staff" }).fill("");

  await page.getByRole("button", { name: "Invite staff" }).click();
  const dialog = page.getByRole("dialog", { name: "Invite staff" });
  await dialog.getByLabel("Name").fill("Raju");
  await dialog.getByLabel("Work email").fill("raju@im.test");
  await dialog.getByRole("button", { name: "Invite" }).click();
  await expect(dialog.getByRole("alert")).toHaveText("Choose at least one role.");
  await dialog.getByRole("checkbox", { name: /^Mechanic/ }).check();
  await dialog.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByTestId("temporary-password")).toHaveText("Tmp-9xQ2-wE7r-Lk4z");
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByTestId("temporary-password")).toHaveCount(0);
  await expect(table.getByRole("row", { name: /Raju/ })).toContainText("Two-factor not set up");

  await page.getByRole("tab", { name: "Customers" }).click();
  const customers = page.getByRole("table", { name: "Customer accounts" });
  await expect(customers).toContainText("******2222");
  await expect(customers).not.toContainText("9811112222");
  await customers.getByRole("button", { name: "Show full number for Ravi Kumar" }).click();
  await expect(customers).toContainText("+919811112222");
  expect(fake.revealed).toEqual(["c1"]);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toBe("customers.csv");
});

test("support agents see customers (masked) but not staff; mechanics have no Users page", async ({ page }) => {
  await new FakeAdmin().as("agent@im.test").install(page);
  await page.goto("/users");
  await expect(page.getByRole("tab")).toHaveCount(0); // one tab only: customers
  await expect(page.getByRole("table", { name: "Customer accounts" })).toContainText("******3333");
  await expect(page.getByRole("table", { name: "Staff accounts" })).toHaveCount(0);
});

test("audit log: filters go to the API, entries show before and after", async ({ page }) => {
  const fake = await new FakeAdmin().as("boss@im.test").install(page);
  await page.goto("/audit");
  const table = page.getByRole("table", { name: /Audit log/ });
  await expect(table.getByRole("row")).toHaveCount(1 + 2);
  await page.getByRole("combobox", { name: "Action" }).selectOption("staff.set_roles");
  await page.getByLabel("Who (email)").fill("boss");
  await page.getByLabel("From").fill("2026-10-30");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(table.getByRole("row")).toHaveCount(1 + 1);
  const q = new URLSearchParams(fake.auditQueries.at(-1));
  expect(q.get("action")).toBe("staff.set_roles");
  expect(q.get("actor")).toBe("boss");
  expect(q.get("since")).toBe("2026-10-29T18:30:00.000Z"); // midnight India time
  await table.getByText("Show").click();
  await expect(table).toContainText('"support_agent"');
});
