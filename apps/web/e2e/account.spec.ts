import { expect, test } from "@playwright/test";

import { CODE, FakeSite } from "../src/__tests__/fake-account";
import { expectNoSideScroll, expectTouchTargets } from "./checks";
import { mockApi } from "./mock-api";

test("log in with a code, see my garage, history and requests, open a request, log out", async ({ page }) => {
  const site = await mockApi(page, new FakeSite());
  await page.goto("/");
  await page.getByTestId("account-link").locator("visible=true").click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText("+91******3210")).toBeVisible();
  await page.getByLabel("6-digit code").fill("000000");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toHaveText("That code is not right. 4 tries left.");
  await expectNoSideScroll(page);
  await expectTouchTargets(page);

  await page.getByLabel("6-digit code").fill(CODE);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole("heading", { name: "My account", exact: true })).toBeVisible();
  await expect(page.getByTestId("garage")).toContainText("Maruti Suzuki Swift");
  await expect(page.getByTestId("history")).toContainText("Slow/pinhole puncture");
  await expect(page.getByTestId("account-link").locator("visible=true")).toHaveText("My account");
  await expectNoSideScroll(page);
  await expectTouchTargets(page);

  await page.getByTestId("my-requests").getByRole("link").click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("IM-7K3Q9P");
  await expect(page.getByTestId("timeline").getByRole("listitem")).toHaveCount(7);
  await expect(page.locator('[aria-current="step"]')).toContainText("Mechanic on the way");
  await expect(page.getByTestId("mechanic")).toHaveText("Your mechanic: Sunita");
  await expect(page.getByTestId("updates").getByRole("listitem")).toHaveCount(5);
  await expectNoSideScroll(page);

  await page.getByRole("link", { name: "Back to my account" }).click();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/$/);
  expect(site.loggedIn).toBe(false);
});

test("account deletion asks for DELETE, then removes everything", async ({ page }) => {
  const site = await mockApi(page, new FakeSite());
  site.loggedIn = true;
  await page.goto("/account");
  await page.getByRole("button", { name: "Delete my account" }).click();
  await expect(page.getByRole("button", { name: "Delete everything" })).toBeDisabled();
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page.getByRole("button", { name: "Delete everything" }).click();
  await expect(page.getByText("Your account is deleted")).toBeVisible();
  expect(site.deleted).toBe(true);
});

test("logged out, /account and a request page send you to log in", async ({ page }) => {
  await mockApi(page, new FakeSite());
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login\?next=%2Faccount$|\/login\?next=\/account$/);
  await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
});

test("the urgent request page keeps Call now on one line", async ({ page }) => {
  await mockApi(page);
  await page.goto("/diagnose");
  await page.getByLabel("Search for your car").fill("swift");
  await page.getByRole("button", { name: /Maruti Suzuki Swift/ }).click();
  await page.getByRole("button", { name: /Flat tyre/ }).click();
  await page.getByRole("button", { name: "No, it is on the road" }).click();
  await page.getByRole("region", { name: "Stay safe while help comes" }).getByRole("link", { name: "Request a Mechanic" }).click();
  const call = page.getByRole("link", { name: "Call now" });
  await expect(call).toBeVisible();
  const lines = await call.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
  });
  expect(lines).toBe(1);
});
