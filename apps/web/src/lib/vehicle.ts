// Vehicle selection helpers: labels, the choices left after each pick, and the saved selection.
import { useMemo, useSyncExternalStore } from "react";

import type { Fuel, Make, PriceSegment, Transmission, Variant } from "@/lib/api";

export const FUEL_LABELS: Record<Fuel, string> = {
  petrol: "Petrol",
  diesel: "Diesel",
  cng: "CNG",
  hybrid: "Hybrid",
  ev: "Electric",
};

export const TRANSMISSION_LABELS: Record<Transmission, string> = {
  mt: "Manual",
  amt: "AMT (automatic)",
  cvt: "CVT (automatic)",
  dct: "DCT (automatic)",
  at: "Automatic (AT)",
};

export const SEGMENT_LABELS: Record<PriceSegment, string> = {
  budget: "Below ₹10 lakh",
  mid: "₹10-25 lakh",
  premium: "Above ₹25 lakh",
};

// Most common makes in Delhi NCR first; the rest follow alphabetically behind "More makes".
export const POPULAR_MAKES = ["Maruti Suzuki", "Hyundai", "Tata", "Mahindra", "Kia", "Toyota", "Honda", "MG"];

export function splitMakes(makes: Make[]): { popular: Make[]; others: Make[] } {
  const rank = (m: Make) => POPULAR_MAKES.indexOf(m.name);
  const popular = makes.filter((m) => rank(m) >= 0).sort((a, b) => rank(a) - rank(b));
  const others = makes.filter((m) => rank(m) < 0).sort((a, b) => a.name.localeCompare(b.name));
  return { popular, others };
}

export function yearRange(yearFrom: number, yearTo: number | null): string {
  return yearTo ? `${yearFrom}-${yearTo}` : `${yearFrom} onwards`;
}

/** Every model year any variant covers, newest first. */
export function yearsOf(variants: Variant[], now = new Date().getFullYear()): number[] {
  const years = new Set<number>();
  for (const v of variants) for (let y = v.year_from; y <= (v.year_to ?? now); y++) years.add(y);
  return [...years].sort((a, b) => b - a);
}

export interface Picks {
  year?: number;
  fuel?: Fuel;
  transmission?: Transmission;
}

/** Variants that match the picks made so far. */
export function matching(variants: Variant[], picks: Picks, now = new Date().getFullYear()): Variant[] {
  return variants.filter(
    (v) =>
      (picks.year === undefined || (v.year_from <= picks.year && picks.year <= (v.year_to ?? now))) &&
      (picks.fuel === undefined || v.fuel === picks.fuel) &&
      (picks.transmission === undefined || v.transmission === picks.transmission),
  );
}

export function unique<T>(items: T[]): T[] {
  return [...new Set(items)];
}

// ---------------------------------------------------------------- the saved selection

/** What the next step sends as `vehicle` to POST /api/diagnosis/sessions, plus a label to show. */
export type VehicleChoice =
  | { kind: "listed"; variant_id: number; label: string; price_segment: PriceSegment }
  | {
      kind: "unlisted";
      unlisted: {
        make: string;
        model: string;
        year: number | null;
        fuel: Fuel | null;
        transmission: Transmission | null;
        price_segment: PriceSegment | null;
      };
      label: string;
    };

export const STORAGE_KEY = "im.diagnosis.vehicle";

export function saveVehicle(choice: VehicleChoice): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(choice));
  } catch {
    // Private mode or storage blocked: the choice still lives in page state.
  }
}

export function loadVehicle(): VehicleChoice | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as VehicleChoice) : null;
  } catch {
    return null;
  }
}

/** The API body for this choice (vehicle field of POST /api/diagnosis/sessions). */
export function vehicleBody(choice: VehicleChoice) {
  return choice.kind === "listed" ? { variant_id: choice.variant_id } : { unlisted: choice.unlisted };
}

const noSubscribe = () => () => {};

/** The saved selection, read without a hydration mismatch (null on the server and during hydration). */
export function useSavedVehicle(): VehicleChoice | null {
  const raw = useSyncExternalStore(
    noSubscribe,
    () => {
      try {
        return sessionStorage.getItem(STORAGE_KEY);
      } catch {
        return null;
      }
    },
    () => null,
  );
  return useMemo(() => {
    try {
      return raw ? (JSON.parse(raw) as VehicleChoice) : null;
    } catch {
      return null;
    }
  }, [raw]);
}
