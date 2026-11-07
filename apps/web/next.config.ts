import path from "node:path";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

import { apiRouting, isDemo } from "../../packages/ui/src/api-proxy";
import { securityHeaders } from "../../packages/ui/src/security-headers";

// The free demo calls the API through this site (API_PROXY_TARGET): packages/ui/src/api-proxy.ts.
const API = apiRouting(process.env);
const DEMO = isDemo(process.env);

// Phase 5.4: CSP and other security headers, from the values this build uses (packages/ui/src/security-headers.ts).
const SECURITY_HEADERS = securityHeaders({
  apiUrl: API.browserApiUrl,
  filesUrl: process.env.NEXT_PUBLIC_FILES_URL ?? "http://localhost:8333",
  sentryDsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  turnstile: Boolean(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY),
  // Phase 5.5: the 3D car's self-hosted Draco decoder (WebAssembly in a blob: worker).
  threeD: true,
  dev: process.env.NODE_ENV === "development",
  referrer: "strict-origin-when-cross-origin",
  camera: true,
});

const nextConfig: NextConfig = {
  env: API.env,
  // Docker images (apps/Dockerfile) build with NEXT_OUTPUT=standalone: a self-contained server.js with only the files
  // it needs, traced from the workspace root so packages/ui is included. Local `next start` (and Playwright) unchanged.
  ...(process.env.NEXT_OUTPUT === "standalone"
    ? { output: "standalone" as const, outputFileTracingRoot: path.join(__dirname, "../..") }
    : {}),
  poweredByHeader: false,
  // Phase 5.5: the landing page and the diagnosis live under app/[locale] (en, hi). English keeps its old addresses
  // (rewritten inside the app, so the address bar shows /diagnose); Hindi is /hi/... ; /en/... redirects to the
  // address without it. Rewrites are plain routing: no proxy runs on each request, and the pages stay static.
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/", destination: "/en" },
        { source: "/diagnose", destination: "/en/diagnose" },
        { source: "/diagnose/:path*", destination: "/en/diagnose/:path*" },
      ],
      afterFiles: API.rewrites,
      fallback: [],
    };
  },
  async redirects() {
    return [
      { source: "/en", destination: "/", permanent: true },
      { source: "/en/:path*", destination: "/:path*", permanent: true },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        // The free demo is never indexed by search engines (NEXT_PUBLIC_DEMO).
        headers: DEMO ? [...SECURITY_HEADERS, { key: "X-Robots-Tag", value: "noindex, nofollow" }] : SECURITY_HEADERS,
      },
      // Phase 5.5: the service worker file is never kept by the browser or a proxy, so each deploy's worker (a new
      // build id) is picked up on the next page load. It is generated: scripts/service-worker.mjs.
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache, no-store, must-revalidate" }] },
    ];
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

// Phase 5.5: next-intl compiles the messages (src/i18n/messages/*.json) at build time, so browsers get them ready to
// use and do not download an ICU message parser.
const withNextIntl = createNextIntlPlugin({
  requestConfig: "./src/i18n/request.ts",
  experimental: { messages: { path: "./src/i18n/messages", format: "json", locales: "infer", precompile: true } },
});

export default withNextIntl(nextConfig);
