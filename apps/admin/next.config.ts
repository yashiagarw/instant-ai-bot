import path from "node:path";
import type { NextConfig } from "next";

// The staff admin app (port 3001). Shared UI comes from the workspace package @im/ui (packages/ui), which
// Turbopack compiles automatically.
const nextConfig: NextConfig = {
  poweredByHeader: false,
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
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Robots-Tag", value: "noindex, nofollow" },
        ],
      },
    ];
  },
};

export default nextConfig;
