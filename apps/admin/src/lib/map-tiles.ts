// Map tiles for the admin map (Requests and Mechanics pages), chosen at build time:
//   NEXT_PUBLIC_MAP_PROVIDER = stadia (default) | maptiler | osm | custom
//   NEXT_PUBLIC_MAP_KEY      = the provider's API key (Stadia: optional on localhost; MapTiler: required)
//   NEXT_PUBLIC_MAP_TILE_URL / NEXT_PUBLIC_MAP_ATTRIBUTION = provider "custom" (any XYZ tile URL)
// Without a key, Stadia serves tiles to localhost only (development). OpenStreetMap's own servers refuse most
// traffic from apps ("Access blocked"): "osm" is for a quick local look only. next.config.ts reads tileHost() so the
// Content-Security-Policy allows exactly this host for images.

export interface TileConfig {
  url: string;
  attribution: string;
  /** The host the browser loads tiles from (for the CSP). */
  origin: string;
}

const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export function tileConfig(env: Record<string, string | undefined>): TileConfig {
  const provider = (env.NEXT_PUBLIC_MAP_PROVIDER || (env.NEXT_PUBLIC_MAP_TILE_URL ? "custom" : "stadia")).toLowerCase();
  const key = env.NEXT_PUBLIC_MAP_KEY || "";
  if (provider === "maptiler") {
    return {
      url: `https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key=${encodeURIComponent(key)}`,
      attribution: `<a href="https://www.maptiler.com/copyright/">&copy; MapTiler</a> ${OSM}`,
      origin: "https://api.maptiler.com",
    };
  }
  if (provider === "osm") {
    return { url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: OSM, origin: "https://tile.openstreetmap.org" };
  }
  if (provider === "custom" && env.NEXT_PUBLIC_MAP_TILE_URL) {
    const url = env.NEXT_PUBLIC_MAP_TILE_URL;
    return { url, attribution: env.NEXT_PUBLIC_MAP_ATTRIBUTION || OSM, origin: new URL(url.replace(/[{}]/g, "")).origin };
  }
  return {
    url: `https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png${key ? `?api_key=${encodeURIComponent(key)}` : ""}`,
    attribution: `&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> ${OSM}`,
    origin: "https://tiles.stadiamaps.com",
  };
}
