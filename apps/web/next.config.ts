import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker images (apps/Dockerfile) build with NEXT_OUTPUT=standalone: a self-contained server.js with only the files
  // it needs, traced from the workspace root so packages/ui is included. Local `next start` (and Playwright) unchanged.
  ...(process.env.NEXT_OUTPUT === "standalone"
    ? { output: "standalone" as const, outputFileTracingRoot: path.join(__dirname, "../..") }
    : {}),
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
