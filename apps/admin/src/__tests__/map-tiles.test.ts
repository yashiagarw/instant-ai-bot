import { expect, test } from "vitest";

import { tileConfig } from "@/lib/map-tiles";

test("Stadia by default (keyless tiles work on localhost), with its key in production", () => {
  const dev = tileConfig({});
  expect(dev.origin).toBe("https://tiles.stadiamaps.com");
  expect(dev.url).not.toContain("api_key");
  expect(dev.attribution).toContain("Stadia Maps");
  const prod = tileConfig({ NEXT_PUBLIC_MAP_KEY: "abc-123" });
  expect(prod.url).toContain("?api_key=abc-123");
});

test("MapTiler needs its key in the URL; OSM and any custom URL are possible", () => {
  const mt = tileConfig({ NEXT_PUBLIC_MAP_PROVIDER: "maptiler", NEXT_PUBLIC_MAP_KEY: "k1" });
  expect(mt.url).toBe("https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key=k1");
  expect(mt.origin).toBe("https://api.maptiler.com");
  expect(tileConfig({ NEXT_PUBLIC_MAP_PROVIDER: "osm" }).origin).toBe("https://tile.openstreetmap.org");
  const custom = tileConfig({ NEXT_PUBLIC_MAP_TILE_URL: "https://tiles.example.com/{z}/{x}/{y}.png", NEXT_PUBLIC_MAP_ATTRIBUTION: "Example" });
  expect([custom.origin, custom.attribution]).toEqual(["https://tiles.example.com", "Example"]);
});
