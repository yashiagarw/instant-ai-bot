import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test, type BrowserContext } from "@playwright/test";

// The whole flow against the real API, database and both apps (nothing mocked): a customer asks for a mechanic on
// the website, a support agent triages it and offers it in the admin app, the mechanic accepts it in the mechanic app
// on a phone, travels, works and records the fault, and the customer's tracking page follows every step by itself.
//
// Opt-in, on its own ports so `pnpm dev` keeps working (README "Phase 5.3"):
//   cd backend && WEB_ORIGIN=http://localhost:3110 ADMIN_ORIGIN=http://localhost:3111 LLM_PROVIDER=none \
//     uv run uvicorn app.main:app --port 8010
//   cd apps/web && E2E_LIVE_FLOW=1 E2E_PORT=3110 NEXT_PUBLIC_API_URL=http://localhost:8010 \
//     pnpm exec playwright test e2e/live-flow.spec.ts --workers=1 --project=desktop
// The config also builds and serves the admin app on :3111. Sign-in screens are skipped: the backend's development
// seed (app.mechanics.e2e_seed) makes a support agent and a verified mechanic with ready sessions. It writes a real
// request into the development database.
test.skip(!process.env.E2E_LIVE_FLOW, "live flow: set E2E_LIVE_FLOW=1 with the API on :8010 (see the top)");
test.setTimeout(180_000);

const API = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010").replace(/\/$/, "");
const ADMIN = process.env.E2E_ADMIN_URL ?? "http://localhost:3111";

type Seed = {
  staff_cookie: { name: string; value: string; path: string };
  mechanic_cookie: { name: string; value: string; path: string };
  mechanic_name: string;
};

function seed(): Seed {
  const backend = path.resolve(__dirname, "../../../backend");
  const out = execFileSync("uv", ["run", "python", "-m", "app.mechanics.e2e_seed"], { cwd: backend, encoding: "utf8" });
  return JSON.parse(out.trim().split("\n").at(-1)!);
}

async function withCookie(context: BrowserContext, cookie: Seed["staff_cookie"]) {
  const host = new URL(API).hostname;
  await context.addCookies([{ ...cookie, domain: host, httpOnly: true, secure: false, sameSite: "Lax" }]);
}

test("customer -> support -> mechanic, with live tracking", async ({ page, browser }) => {
  const s = seed();
  const first = s.mechanic_name.split(" ")[0];

  // 1. Customer: the request form, then the live tracking page.
  await page.goto("/request");
  await page.getByLabel("Your name", { exact: true }).fill("Asha Verma");
  await page.getByLabel("Mobile number", { exact: true }).fill("98000 01234");
  await page.getByRole("group", { name: "How should we help?" }).getByText("At my location").click();
  await page.getByLabel("Area, sector or landmark").fill("Malviya Nagar");
  await page.getByLabel("Pincode").fill("110017");
  await page.getByRole("checkbox", { name: /Instant Mechanic's team may use/ }).check();
  await page.getByRole("button", { name: "Request a Mechanic" }).click();
  const reference = (await page.getByTestId("reference").textContent())!.trim();
  await page.getByTestId("track-link").click();
  await expect(page.getByTestId("track-status")).toHaveText("Request received");

  // 2. Support (admin app): triage, then offer to the seeded mechanic.
  const supportCtx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await withCookie(supportCtx, s.staff_cookie);
  const support = await supportCtx.newPage();
  await support.goto(`${ADMIN}/requests`);
  await support.getByRole("link", { name: reference }).click();
  await expect(support.getByRole("heading", { level: 1 })).toHaveText(reference);
  await support.getByRole("button", { name: "Mark triaged" }).click();
  await expect(support.getByTestId("request-status")).toHaveText("Triaged");
  await support.getByRole("button", { name: `Offer job to ${s.mechanic_name}` }).click();
  await expect(support.getByTestId("open-assignment")).toContainText(`${s.mechanic_name} was offered the job`);
  await expect(support.getByTestId("offer-expires")).toBeVisible();
  await expect(page.getByTestId("track-status")).toHaveText("Finding a mechanic for you", { timeout: 20_000 });

  // 3. Mechanic (the app on a small phone, Hindi): the offer shows no address; accept, then the job.
  const mechCtx = await browser.newContext({ viewport: { width: 360, height: 640 }, hasTouch: true, isMobile: true });
  await withCookie(mechCtx, s.mechanic_cookie);
  const mech = await mechCtx.newPage();
  await mech.goto("/m/offers");
  const offer = mech.getByTestId("offer").filter({ hasText: reference });
  await expect(offer).toContainText("pincode 110017");
  await expect(offer).not.toContainText("Asha");
  await offer.getByRole("button", { name: "काम लें" }).click();
  await expect(mech.getByTestId("job-address")).toContainText("110017");
  await expect(mech.getByTestId("job-phone")).toHaveText("+91******1234");
  await mech.getByRole("button", { name: "20 मिनट" }).click();
  await mech.getByRole("button", { name: "निकल रहा हूँ" }).click();
  await expect(mech.getByTestId("job-status")).toHaveText("रास्ते में");

  // The customer's page caught up by itself: the mechanic's first name, their estimate, a masked call button.
  await expect(page.getByTestId("track-status")).toHaveText("Mechanic on the way", { timeout: 20_000 });
  await expect(page.getByTestId("track-mechanic")).toContainText(first);
  await expect(page.getByTestId("track-eta")).toHaveText(/Arriving in about (19|20) minutes/);
  await expect(page.getByRole("button", { name: `Call ${first}` })).toBeVisible();

  await mech.getByRole("button", { name: "पहुँच गया" }).click();
  await mech.getByRole("button", { name: "काम शुरू" }).click();
  await mech.getByRole("radio", { name: /दूसरी \/ पक्का नहीं/ }).click();
  await mech.getByLabel("क्या मिला? छोटा नोट लिखें").fill("Loose battery terminal, tightened");
  await mech.getByRole("button", { name: "पूरा करें और भेजें" }).click();
  await expect(mech.getByRole("status")).toContainText("काम पूरा हुआ");

  await expect(page.getByTestId("track-status")).toHaveText("Done", { timeout: 20_000 });

  // Support sees the mechanic's own steps in the timeline.
  await support.reload();
  await expect(support.getByTestId("request-status")).toHaveText("Completed");
  await expect(support.getByRole("list", { name: "Timeline" })).toContainText(`${first} (mechanic, app)`);
  await supportCtx.close();
  await mechCtx.close();
});
