import { describe, expect, test } from "vitest";

import { apiRouting, isDemo } from "./api-proxy";
import { securityHeaders } from "./security-headers";

describe("apiRouting (the free demo's same-origin API)", () => {
  test("without API_PROXY_TARGET nothing changes (docker-compose, local development)", () => {
    expect(apiRouting({})).toEqual({ browserApiUrl: "http://localhost:8000", rewrites: [], env: {} });
    expect(apiRouting({ NEXT_PUBLIC_API_URL: "https://api.instantmechanic.online" }).browserApiUrl).toBe(
      "https://api.instantmechanic.online",
    );
  });

  test("with it, /api and /media go to the API through this site and the browser uses its own origin", () => {
    const r = apiRouting({ API_PROXY_TARGET: "https://im-api.onrender.com/", NEXT_PUBLIC_API_URL: "https://x.test" });
    expect(r.browserApiUrl).toBe("");
    expect(r.env).toEqual({ NEXT_PUBLIC_API_URL: "" });
    expect(r.rewrites).toEqual([
      { source: "/api/:path*", destination: "https://im-api.onrender.com/api/:path*" },
      { source: "/media/:path*", destination: "https://im-api.onrender.com/media/:path*" },
    ]);
  });

  test("a target that is not an origin is refused at build time", () => {
    expect(() => apiRouting({ API_PROXY_TARGET: "im-api.onrender.com" })).toThrow(/origin/);
    expect(() => apiRouting({ API_PROXY_TARGET: "https://im-api.onrender.com/api" })).toThrow(/origin/);
  });

  test("the CSP then allows the API only on 'self'", () => {
    const csp = securityHeaders({ apiUrl: "", dev: false, referrer: "same-origin" }).find((h) => h.key === "Content-Security-Policy")!.value;
    const connect = csp.split(";").find((d) => d.trim().startsWith("connect-src"))!;
    expect(connect).toContain("'self'");
    expect(connect).not.toContain("onrender");
  });
});

test("isDemo", () => {
  expect(isDemo({})).toBe(false);
  expect(isDemo({ NEXT_PUBLIC_DEMO: "1" })).toBe(true);
  expect(isDemo({ NEXT_PUBLIC_DEMO: "true" })).toBe(true);
  expect(isDemo({ NEXT_PUBLIC_DEMO: "0" })).toBe(false);
});
