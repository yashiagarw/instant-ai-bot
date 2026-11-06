"use client";

import { useTranslations } from "next-intl";

import type { Fuel, PriceSegment, Transmission } from "@/lib/api";

/** Fuel, gearbox and price-range names in the page's language (lib/vehicle.ts keeps the English constants). */
export function useVehicleLabels() {
  const t = useTranslations("common");
  return {
    fuel: (f: Fuel) => t(`fuel.${f}`),
    transmission: (x: Transmission) => t(`transmission.${x}`),
    segment: (s: PriceSegment) => t(`segment.${s}`),
  };
}
