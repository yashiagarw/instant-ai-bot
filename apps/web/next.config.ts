import path from "node:path";
import type { NextConfig } from "next";

import { securityHeaders } from "../../packages/ui/src/security-headers";

// Phase 5.4: CSP and other security headers, from the values this build uses (packages/ui/src/security-headers.ts).
const SECURITY_HEADERS = securityHeaders({
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  filesUrl: process.env.NEXT_PUBLIC_FILES_URL ?? "http://localhost:8333",
  sentryDsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  turnstile: Boolean(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY),
  dev: process.env.NODE_ENV === "development",
  referrer: "strict-origin-when-cross-origin",
  camera: true,
});

const nextConfig: NextConfig = {
  // Docker images (apps/Dockerfile) build with NEXT_OUTPUT=standalone: a self-contained server.js with only the files
  // it needs, traced from the workspace root so packages/ui is included. Local `next start` (and Playwright) unchanged.
  ...(process.env.NEXT_OUTPUT === "standalone"
    ? { output: "standalone" as const, outputFileTracingRoot: path.join(__dirname, "../..") }
    : {}),
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
