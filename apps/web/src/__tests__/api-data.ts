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
export const CATEGORIES: CategoriesResult = {
  categories: [],
  topics: [
    { code: "flat_tyre", type: "emergency", label: "Flat tyre", mode: "fast_track", categories: ["tyre"] },
    { code: "book_inspection", type: "inspection", label: "Book an inspection", mode: "inspect", categories: [] },
    { code: "tyres", type: "tile", label: "Tyres", mode: "diagnose", categories: ["tyre"] },
    { code: "ac", type: "tile", label: "AC not cooling", mode: "diagnose", categories: ["ac"] },
  ],
};
