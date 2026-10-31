import { expect, type Page, test } from "@playwright/test";

import { FakePhotos, RED_OIL_LIGHT } from "../src/__tests__/fake-photos";
import { expectNoSideScroll, expectTouchTargets } from "./checks";
import { mockApi } from "./mock-api";

// A 1x1 PNG: the storage and the API are mocked, so any real image will do.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);
const PICTURE = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 30"><rect width="40" height="30" fill="#ffe6d3"/></svg>`;

async function chat(page: Page) {
  const photos = await mockApi(page, new FakePhotos());
  await page.route("https://storage.test/**", async (route) => {
    if (route.request().method() === "POST") return route.fulfill({ status: 204, body: "" });
    return route.fulfill({ contentType: "image/svg+xml", body: PICTURE });
  });
  await page.goto("/diagnose");
  await page.getByLabel("Search for your car").fill("swift");
  await page.getByRole("button", { name: /Maruti Suzuki Swift/ }).click();
  await page.getByRole("button", { name: /^Tyres/ }).click();
  await expect(page.getByText("Question 1 of about 8")).toBeVisible();
  return photos;
}

test("photo step: camera or gallery, preview, upload progress, then the photo; questions keep working", async ({
  page,
  isMobile,
}) => {
  const photos = await chat(page);
  const step = page.getByTestId("photo-step");
  await expect(step.getByRole("heading", { name: /Add a photo/ })).toBeVisible();
  if (isMobile) {
    await expect(step.getByRole("button", { name: "Take a photo" })).toBeVisible();
    await expect(step.getByRole("button", { name: "Choose from gallery" })).toBeVisible();
  } else {
    await expect(step.getByRole("button", { name: "Choose a photo" })).toBeVisible();
    await expect(step.getByRole("button", { name: "Take a photo" })).toHaveCount(0);
  }
  await expectNoSideScroll(page);
  await expectTouchTargets(page);

  // Pick a photo, see it, retake, then use it.
  await step.getByTestId("gallery-input").setInputFiles({ name: "first.png", mimeType: "image/png", buffer: PNG });
  await expect(step.getByRole("img", { name: "Preview of your photo" })).toBeVisible();
  await step.getByTestId(isMobile ? "camera-input" : "gallery-input").setInputFiles({
    name: "second.png",
    mimeType: "image/png",
    buffer: PNG,
  });
  await step.getByRole("button", { name: "Use this photo" }).click();
  await expect(step.getByTestId("photo-status")).toContainText("Photo added");
  await expect(step.getByRole("img", { name: "Your photo 1" })).toBeVisible();
  expect(photos.photos).toHaveLength(1);
  // No vision provider (the default): the photo is kept and a mechanic looks at it.
  await expect(step.getByText("A mechanic will look at your photo.")).toBeVisible();

  // A wrong file is explained and does not stop anything.
  await step.getByTestId("gallery-input").setInputFiles({ name: "notes.pdf", mimeType: "application/pdf", buffer: PNG });
  await expect(step.getByRole("alert")).toContainText("JPEG, PNG, WebP or HEIC");

  // The questions carry on regardless.
  await page.getByRole("button", { name: "The tyre goes soft again after I fill it with air" }).click();
  await expect(page.getByText("Question 2 of about 8")).toBeVisible();
  await expect(page.getByTestId("photos")).toBeVisible(); // the photo is still there for this diagnosis
});

test("the photo step can be skipped and the diagnosis finishes without a photo", async ({ page }) => {
  await chat(page);
  await page.getByTestId("photo-step").getByRole("button", { name: "Skip" }).click();
  await expect(page.getByText("No photo added.")).toBeVisible();
  await page.getByRole("button", { name: "The tyre goes soft again after I fill it with air" }).click();
  await page.getByRole("button", { name: "Not sure" }).click();
  await expect(page).toHaveURL(/\/result$/);
});

test("a red warning light in a photo: Possible ..., a note to verify, and the safety banner", async ({ page }) => {
  const photos = await chat(page);
  photos.analysis = RED_OIL_LIGHT;
  const step = page.getByTestId("photo-step");
  await step.getByTestId("gallery-input").setInputFiles({ name: "dash.png", mimeType: "image/png", buffer: PNG });
  await step.getByRole("radio", { name: "A warning light on the dashboard" }).check();
  await step.getByRole("button", { name: "Use this photo" }).click();
  await expect(step.getByText("Possible: Engine oil pressure light")).toBeVisible();
  await expect(step.getByText(/Photos can be misleading/)).toBeVisible();
  await expect(step.getByTestId("safety-banner")).toContainText("Stop now and switch off the engine");
  expect(photos.analyzed).toEqual(["warning_light"]);
  await expectNoSideScroll(page);
  await expectTouchTargets(page);
});

test("the results page shows the customer's photos", async ({ page }) => {
  const photos = await chat(page);
  photos.analysis = RED_OIL_LIGHT;
  const step = page.getByTestId("photo-step");
  await step.getByTestId("gallery-input").setInputFiles({ name: "dash.png", mimeType: "image/png", buffer: PNG });
  await step.getByRole("button", { name: "Use this photo" }).click();
  await expect(step.getByTestId("photo-status")).toContainText("Photo added");
  await page.getByRole("button", { name: "The tyre goes soft again after I fill it with air" }).click();
  await page.getByRole("button", { name: "Not sure" }).click();
  await expect(page).toHaveURL(/\/result$/);
  const gallery = page.getByTestId("photo-gallery").locator("visible=true");
  await expect(gallery.getByRole("img", { name: "Your photo 1" })).toBeVisible();
  await expect(gallery.getByText("Possible: Engine oil pressure light")).toBeVisible();
  await expect(page.locator("#result-safety")).toContainText("Stop now and switch off the engine");
  await expectNoSideScroll(page);
});
