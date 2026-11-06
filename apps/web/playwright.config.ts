import { defineConfig, devices } from "@playwright/test";

// The API is mocked in each test (page.route), so the backend does not need to run (except e2e/live.spec.ts, which
// is opt-in). The app runs as a production build on its own port, separate from `pnpm dev`; E2E_PORT and
// NEXT_PUBLIC_API_URL change the port and the API it calls (for the live test).
const PORT = Number(process.env.E2E_PORT ?? 3100);
// E2E_BASE_URL: test an already running deployment instead (e.g. the local production stack at https://localhost,
// self-signed: e2e/prod-smoke.spec.ts). No server is started then.
const BASE_URL = process.env.E2E_BASE_URL;
// E2E_LIVE_FLOW: the customer -> support -> mechanic flow against the real API (e2e/live-flow.spec.ts) also needs the
// admin app: built and served on E2E_ADMIN_PORT (3111) with the same NEXT_PUBLIC_API_URL.
const ADMIN_PORT = Number(process.env.E2E_ADMIN_PORT ?? 3111);
// The Content-Security-Policy allows only the photo storage host (NEXT_PUBLIC_FILES_URL): the mocked tests serve
// photos from https://storage.test (e2e/photos.spec.ts), live runs use the real one from the environment.
const FILES_URL = process.env.NEXT_PUBLIC_FILES_URL ?? "https://storage.test";
const web = {
  command: `pnpm build && pnpm start --port ${PORT}`,
  env: { NEXT_PUBLIC_FILES_URL: FILES_URL },
  url: `http://localhost:${PORT}`,
  reuseExistingServer: !process.env.CI,
  timeout: 180_000,
};
const admin = {
  command: `pnpm --dir ../admin build && pnpm --dir ../admin start --port ${ADMIN_PORT}`,
  url: `http://localhost:${ADMIN_PORT}/login`,
  reuseExistingServer: !process.env.CI,
  timeout: 240_000,
};

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL ?? `http://localhost:${PORT}`,
    ignoreHTTPSErrors: !!BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "mobile", use: { ...devices["Pixel 7"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } },
  ],
  webServer: BASE_URL ? undefined : process.env.E2E_LIVE_FLOW ? [web, admin] : web,
});
