// The free demo (docs/deploy-free-demo.md): the web and admin apps on Vercel call the API through their own domain,
// so login cookies are first-party on *.vercel.app. With API_PROXY_TARGET set (the API's address, e.g.
// https://im-api.onrender.com; read at build time, never sent to browsers):
//   - /api/* and /media/* on the app's own domain are rewritten to the API (Next.js rewrites, done by Vercel's edge);
//   - the browser code calls the API on its own origin (NEXT_PUBLIC_API_URL becomes ""), so the CSP needs only 'self'.
// Without it (docker-compose, local development) nothing changes: the browser calls NEXT_PUBLIC_API_URL directly.

export interface ApiRouting {
  /** What the browser code uses as the API base ("" = this site). */
  browserApiUrl: string;
  /** Next.js rewrites to the API, or none. */
  rewrites: { source: string; destination: string }[];
  /** For next.config `env`: forces NEXT_PUBLIC_API_URL to "" in the browser bundle when proxying. */
  env: Record<string, string>;
}

export function apiRouting(env: Record<string, string | undefined>): ApiRouting {
  const target = (env.API_PROXY_TARGET ?? "").trim().replace(/\/$/, "");
  if (!target) {
    return { browserApiUrl: env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000", rewrites: [], env: {} };
  }
  if (!/^https?:\/\/[^/]+$/.test(target)) {
    throw new Error(`API_PROXY_TARGET must be an origin like https://im-api.onrender.com, got ${target}`);
  }
  return {
    browserApiUrl: "",
    rewrites: [
      { source: "/api/:path*", destination: `${target}/api/:path*` },
      { source: "/media/:path*", destination: `${target}/media/:path*` },
    ],
    env: { NEXT_PUBLIC_API_URL: "" },
  };
}

/** NEXT_PUBLIC_DEMO=1: the free demo (banner, noindex). */
export function isDemo(env: Record<string, string | undefined>): boolean {
  return ["1", "true", "yes"].includes((env.NEXT_PUBLIC_DEMO ?? "").toLowerCase());
}
