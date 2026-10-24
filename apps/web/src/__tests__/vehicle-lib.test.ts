import { expect, test } from "vitest";

import { matching, splitMakes, vehicleBody, yearsOf } from "@/lib/vehicle";
import { MAKES, VARIANTS } from "./api-mock";

test("popular makes come first in Delhi NCR order, the rest alphabetically", () => {
  const { popular, others } = splitMakes(MAKES);
  expect(popular.map((m) => m.name)).toEqual(["Maruti Suzuki", "Hyundai", "Tata"]);
  expect(others.map((m) => m.name)).toEqual(["BMW"]);
});

test("years cover every variant, newest first; picks narrow the variants", () => {
  expect(yearsOf(VARIANTS, 2026)).toEqual([2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]);
  expect(matching(VARIANTS, { year: 2020 }, 2026).map((v) => v.id)).toEqual([10, 11]);
  expect(matching(VARIANTS, { year: 2025, fuel: "petrol", transmission: "amt" }, 2026).map((v) => v.id)).toEqual([16]);
});

test("the API body is variant_id for a listed car and the typed details for an unlisted one", () => {
  expect(vehicleBody({ kind: "listed", variant_id: 16, label: "x", price_segment: "budget" })).toEqual({ variant_id: 16 });
  const unlisted = { make: "Hindustan", model: "Ambassador", year: 2010, fuel: null, transmission: "mt" as const, price_segment: null };
  expect(vehicleBody({ kind: "unlisted", unlisted, label: "x" })).toEqual({ unlisted });
});
