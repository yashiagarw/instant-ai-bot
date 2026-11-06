"use client";

// A Leaflet map. Tiles come from the provider configured at build time (src/lib/map-tiles.ts: Stadia by default,
// MapTiler with a key). Leaflet needs the browser, so it is loaded after the first render. The map only
// illustrates: every point is also listed as text next to it, so nothing depends on seeing the map.

import "leaflet/dist/leaflet.css";

import { useEffect, useRef } from "react";
import type { Map as LeafletMap, LayerGroup } from "leaflet";

import { cn } from "@im/ui/cn";

import { tileConfig } from "@/lib/map-tiles";

const TILES = tileConfig({
  NEXT_PUBLIC_MAP_PROVIDER: process.env.NEXT_PUBLIC_MAP_PROVIDER,
  NEXT_PUBLIC_MAP_KEY: process.env.NEXT_PUBLIC_MAP_KEY,
  NEXT_PUBLIC_MAP_TILE_URL: process.env.NEXT_PUBLIC_MAP_TILE_URL,
  NEXT_PUBLIC_MAP_ATTRIBUTION: process.env.NEXT_PUBLIC_MAP_ATTRIBUTION,
});
const TILE_URL = TILES.url;
const ATTRIBUTION = TILES.attribution;
const DELHI: [number, number] = [28.6139, 77.209];

const TONES = {
  request: "#c62828", // the customer's car (danger red: a request can be safety-critical)
  mechanic: "#d9620f",
  zone: "#15120f",
} as const;

export interface MapPoint {
  id: string;
  lat: number;
  lon: number;
  label: string;
  tone: keyof typeof TONES;
  /** An estimated point (GeoNames accuracy 1, or only the zone's centre): drawn dashed and labelled. */
  rough?: boolean;
}

export interface MapCircle {
  id: string;
  lat: number;
  lon: number;
  radiusKm: number;
  label: string;
}

export function MapView({
  label,
  points,
  circles = [],
  onPick,
  className,
}: {
  /** The map's accessible name. */
  label: string;
  points: MapPoint[];
  circles?: MapCircle[];
  /** Clicking the map gives a point (e.g. a zone's centre). */
  onPick?: (lat: number, lon: number) => void;
  className?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const layer = useRef<LayerGroup | null>(null);
  const leaflet = useRef<typeof import("leaflet") | null>(null);
  const pick = useRef(onPick);
  useEffect(() => {
    pick.current = onPick;
  }, [onPick]);

  // Draws the points and circles (again after every change) once Leaflet is loaded.
  const draw = useRef<() => void>(() => undefined);
  useEffect(() => {
    draw.current = () => {
      const L = leaflet.current;
      if (!L || !map.current || !layer.current) return;
      layer.current.clearLayers();
      const bounds: [number, number][] = [];
      for (const c of circles) {
        L.circle([c.lat, c.lon], { radius: c.radiusKm * 1000, color: TONES.zone, weight: 1, fillOpacity: 0.08 })
          .bindTooltip(c.label)
          .addTo(layer.current);
        const dLat = c.radiusKm / 111;
        bounds.push([c.lat - dLat, c.lon], [c.lat + dLat, c.lon]);
      }
      for (const p of points) {
        L.circleMarker([p.lat, p.lon], {
          radius: p.tone === "request" ? 10 : 8,
          color: TONES[p.tone],
          weight: 3,
          dashArray: p.rough ? "4 4" : undefined,
          fillColor: TONES[p.tone],
          fillOpacity: p.rough ? 0.25 : 0.7,
        })
          .bindTooltip(p.rough ? `${p.label} (rough location)` : p.label)
          .addTo(layer.current);
        bounds.push([p.lat, p.lon]);
      }
      if (bounds.length === 1) map.current.setView(bounds[0], 12);
      else if (bounds.length > 1) map.current.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
    };
    draw.current();
  }, [points, circles]);

  useEffect(() => {
    let cancelled = false;
    void import("leaflet").then((mod) => {
      const L = (mod as unknown as { default?: typeof import("leaflet") }).default ?? mod;
      if (cancelled || !box.current || map.current) return;
      leaflet.current = L;
      map.current = L.map(box.current, { center: DELHI, zoom: 10, scrollWheelZoom: false });
      L.tileLayer(TILE_URL, { attribution: ATTRIBUTION, maxZoom: 18 }).addTo(map.current);
      layer.current = L.layerGroup().addTo(map.current);
      map.current.on("click", (e) => pick.current?.(Number(e.latlng.lat.toFixed(5)), Number(e.latlng.lng.toFixed(5))));
      draw.current();
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      layer.current = null;
    };
  }, []);

  return (
    // isolate: Leaflet's panes have high z-indexes; keep them under the sticky header and dialogs.
    <div
      ref={box}
      role="region"
      aria-label={label}
      data-testid="map"
      className={cn("isolate h-72 w-full overflow-hidden rounded-2xl border border-border bg-warm-white sm:h-96", onPick && "cursor-crosshair", className)}
    />
  );
}
