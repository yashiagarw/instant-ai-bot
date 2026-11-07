import path from "node:path";
import type { NextConfig } from "next";

import { apiRouting } from "../../packages/ui/src/api-proxy";
import { securityHeaders } from "../../packages/ui/src/security-headers";
import { tileConfig } from "./src/lib/map-tiles";

// Phase 5.4: CSP and other security headers, from the values this build uses (packages/ui/src/security-headers.ts),
// with the map tile host of the configured provider (src/lib/map-tiles.ts).
// The free demo calls the API through this site (API_PROXY_TARGET): packages/ui/src/api-proxy.ts.
const API = apiRouting(process.env);

const SECURITY_HEADERS = securityHeaders({
  apiUrl: API.browserApiUrl,
  filesUrl: process.env.NEXT_PUBLIC_FILES_URL ?? "http://localhost:8333",
  sentryDsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  extraImg: [tileConfig(process.env).origin],
  dev: process.env.NODE_ENV === "development",
  referrer: "same-origin",
});

// The staff admin app (port 3001). Shared UI comes from the workspace package @im/ui (packages/ui), which
// Turbopack compiles automatically.
const nextConfig: NextConfig = {
  env: API.env,
  poweredByHeader: false,
  async rewrites() {
    return API.rewrites;
  },
  // Docker images (apps/Dockerfile) build with NEXT_OUTPUT=standalone: a self-contained server.js with only the files
  // it needs, traced from the workspace root so packages/ui is included. Local `next start` (and Playwright) unchanged.
  ...(process.env.NEXT_OUTPUT === "standalone"
    ? { output: "standalone" as const, outputFileTracingRoot: path.join(__dirname, "../..") }
    : {}),
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [...SECURITY_HEADERS, { key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
    ];
  },
};

export default nextConfig;
