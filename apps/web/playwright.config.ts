import { defineConfig, devices } from "@playwright/test";

// The API is mocked in each test (page.route), so the backend does not need to run (except e2e/live.spec.ts, which
// is opt-in). The app runs as a production build on its own port, separate from `pnpm dev`; E2E_PORT and
// NEXT_PUBLIC_API_URL change the port and the API it calls (for the live test).
const PORT = Number(process.env.E2E_PORT ?? 3100);
// E2E_BASE_URL: test an already running deployment instead (e.g. the local production stack at https://localhost,
// self-signed: e2e/prod-smoke.spec.ts). No server is started then.
const BASE_URL = process.env.E2E_BASE_URL;

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
  webServer: BASE_URL
    ? undefined
    : {
        command: `pnpm build && pnpm start --port ${PORT}`,
        url: `http://localhost:${PORT}`,
        reuseExistingServer: !process.env.CI,
        timeout: 180_000,
      },
});
