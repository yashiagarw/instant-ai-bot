// Sample API responses shared by the Vitest mocks and the Playwright tests.
import type { CategoriesResult, Make, Model, SearchResult, Variant } from "../lib/api";

export const MAKES: Make[] = [
  { id: 13, name: "BMW" },
  { id: 2, name: "Hyundai" },
  { id: 1, name: "Maruti Suzuki" },
  { id: 3, name: "Tata" },
];
export const MODELS: Model[] = [
  { id: 5, make_id: 1, name: "Swift", body_type: "hatchback" },
  { id: 6, make_id: 1, name: "Dzire", body_type: "sedan" },
];
export const VARIANTS: Variant[] = [
  { id: 15, model_id: 5, name: "Petrol 1.2 MT", fuel: "petrol", transmission: "mt", engine: "1.2", year_from: 2024, year_to: null, price_segment: "budget" },
  { id: 16, model_id: 5, name: "Petrol 1.2 AMT", fuel: "petrol", transmission: "amt", engine: "1.2", year_from: 2024, year_to: null, price_segment: "budget" },
  { id: 17, model_id: 5, name: "CNG MT", fuel: "cng", transmission: "mt", engine: "1.2", year_from: 2024, year_to: null, price_segment: "budget" },
  { id: 10, model_id: 5, name: "Petrol MT (old)", fuel: "petrol", transmission: "mt", engine: "1.2 K12", year_from: 2018, year_to: 2023, price_segment: "budget" },
  { id: 11, model_id: 5, name: "Petrol MT ZXi", fuel: "petrol", transmission: "mt", engine: "1.2 ZXi", year_from: 2018, year_to: 2023, price_segment: "mid" },
];
export const SEARCH: SearchResult = {
  query: "swift",
  year_matched: true,
  results: [
    { variant_id: 16, make: "Maruti Suzuki", model: "Swift", model_id: 5, variant: "Petrol 1.2 AMT", fuel: "petrol", transmission: "amt", year_from: 2024, year_to: null, price_segment: "budget", score: 2 },
  ],
};
const EMERGENCY: [string, string, string, boolean][] = [
  ["battery_dead", "Battery dead", "बैटरी डाउन", false],
  ["flat_tyre", "Flat tyre", "टायर पंक्चर", false],
  ["out_of_fuel", "Petrol finished", "पेट्रोल खत्म", true],
  ["locked_out", "Locked out", "चाबी अंदर, गाड़ी लॉक", true],
  ["car_stuck", "Car stuck", "गाड़ी फंस गई", true],
  ["car_in_water", "Car in water", "गाड़ी पानी में", true],
  ["accident_tow", "Accident / tow", "एक्सीडेंट / टोइंग", true],
  ["smoke", "Smoke or burning smell", "धुआं या जलने की बदबू", true],
];

export const CATEGORIES: CategoriesResult = {
  categories: [],
  topics: [
    ...EMERGENCY.map(([code, label, label_hi, beta]) => ({
      code,
      type: "emergency" as const,
      label,
      label_hi,
      beta,
      mode: "fast_track" as const,
      categories: ["x"],
    })),
    { code: "book_inspection", type: "inspection", label: "Book an inspection", label_hi: "जांच बुक करें", beta: true, mode: "inspect", categories: [] },
    { code: "tyres", type: "tile", label: "Tyres", label_hi: "टायर", beta: false, mode: "diagnose", categories: ["tyre"] },
    { code: "ac", type: "tile", label: "AC not cooling", label_hi: "AC ठंडा नहीं", beta: false, mode: "diagnose", categories: ["ac"] },
    { code: "ev_hybrid", type: "tile", label: "EV & hybrid", label_hi: "EV और हाइब्रिड", beta: true, mode: "diagnose", categories: ["ev_hybrid"] },
  ],
};

/** GET /api/categories for a car: like the real API, EV wording for out_of_fuel and no EV tile on other fuels. */
export function categoriesFor(url: URL): CategoriesResult {
  const fuel = url.searchParams.get("fuel") ?? (url.searchParams.get("variant_id") ? "petrol" : null);
  const topics = CATEGORIES.topics
    .filter((t) => !(t.code === "ev_hybrid" && fuel && fuel !== "ev" && fuel !== "hybrid"))
    .map((t) =>
      t.code === "out_of_fuel" && fuel === "ev"
        ? { ...t, label: "Battery ran out", label_hi: "बैटरी चार्ज खत्म", categories: ["ev_hybrid"] }
        : t,
    );
  return { categories: [], topics };
}
