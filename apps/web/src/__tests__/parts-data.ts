// Fake parts and estimates (GET /api/estimates, /api/faults/{key}/parts, /api/parts/{id}, /api/parts/compare) for the
// tyre faults of fake-diagnosis.ts: F04-TY-02 has a part listed for the car, a segment part whose fit is not verified
// and an aftermarket one; F04-TY-04 has no price data ("not enough data").

import type { Estimates, FaultEstimate, FaultParts, Part, PartCompare, PartDetail, PartPrice } from "@/lib/api";

const price = (amount: number, extra: Partial<PartPrice> = {}): PartPrice => ({
  segment: "budget",
  price_inr: amount,
  price_max_inr: null,
  approx_label: "Price checked online",
  verification: "checked",
  checked_on: "2026-10-22",
  model_verified: true,
  price_basis: "MRP / website price",
  gst_text: "Incl. (as shown)",
  gst_included: true,
  fitting_included: false,
  supplier: "Maruti Genuine Parts",
  source_url: null,
  note: null,
  ...extra,
});

export const PARTS: Part[] = [
  {
    id: 101,
    name: "Tyre valve (tubeless)",
    part_type: "Tyre valve",
    brand: { name: "Maruti Genuine", kind: "oem" },
    part_number: "43150M66R00",
    quantity: 1,
    generic: false,
    fit: { status: "listed", label: "Listed for your car" },
    listed_for: ["Maruti Suzuki Swift 2024-"],
    in_total: true,
    prices: [price(185)],
    images: [{ file: "F04/valve.svg", caption: "Tubeless tyre valve", image_type: "drawn guide picture" }],
  },
  {
    id: 102,
    name: "Puncture repair kit (plug type)",
    part_type: "Puncture repair kit",
    brand: null,
    part_number: null,
    quantity: 1,
    generic: true,
    fit: { status: "not_verified", label: "Fit not verified for your car" },
    listed_for: [],
    in_total: true,
    prices: [price(250, { price_max_inr: 1400, approx_label: "Approx price, ask the shop", verification: "approx", checked_on: null, model_verified: false })],
    images: [],
  },
  {
    id: 103,
    name: "Tyre sealant",
    part_type: "Tyre sealant",
    brand: { name: "Slime", kind: "aftermarket" },
    part_number: "SL-10004",
    quantity: 1,
    generic: false,
    fit: { status: "not_verified", label: "Fit not verified for your car" },
    listed_for: ["Hyundai Creta 2020-2024"],
    in_total: false,
    prices: [price(1234567, { approx_label: "Listed price, check again", verification: "listed_recheck" })],
    images: [],
  },
];

export function faultParts(url: URL): FaultParts {
  const key = decodeURIComponent(url.pathname.split("/")[3]);
  const variant = Number(url.searchParams.get("variant_id")) || null;
  const parts = key === "F04-TY-02" ? PARTS : [];
  return {
    fault_key: key,
    requested_key: key,
    fault_name: key,
    vehicle: variant
      ? { variant_id: variant, name: "Maruti Suzuki Swift Petrol 1.2 AMT", fuel: "petrol", transmission: "amt", price_segment: "budget" }
      : null,
    segment: "budget",
    coverage_level: "part_fit_verified",
    // Without a car nothing is shown as fitting.
    parts: variant ? parts : parts.map((p) => ({ ...p, fit: { status: "not_verified", label: "Fit not verified for your car" } })),
    disclaimer: "This is an estimate based on your answers and our data.",
  };
}

function detail(p: Part, variant: number | null): PartDetail {
  return {
    ...p,
    fit: variant ? p.fit : { status: "not_verified", label: "Fit not verified for your car" },
    compatibility:
      p.id === 101 ? [{ make: "Maruti Suzuki", model: "Swift", year_from: 2024, year_to: null, fuel: null, transmission: null, status: "listed" }] : [],
    faults: [{ fault_key: "F04-TY-02", name: "Slow/pinhole puncture", segment: "budget" }],
  };
}

export function partDetail(url: URL): PartDetail | "missing" {
  const id = Number(url.pathname.split("/").pop());
  const p = PARTS.find((x) => x.id === id);
  return p ? detail(p, Number(url.searchParams.get("variant_id")) || null) : "missing";
}

export function compare(url: URL): PartCompare {
  const variant = Number(url.searchParams.get("variant_id")) || null;
  const ids = (url.searchParams.get("ids") ?? "").split(",").map(Number);
  return {
    vehicle: null,
    parts: PARTS.filter((p) => ids.includes(p.id)).map((p) => detail(p, variant)),
    disclaimer: "This is an estimate based on your answers and our data.",
  };
}

const ZONES = { delhi: "Delhi", noida: "Noida", gurugram: "Gurugram", ghaziabad: "Ghaziabad", faridabad: "Faridabad" } as const;
const PINCODES: Record<string, keyof typeof ZONES> = { "201309": "noida", "122002": "gurugram" };

function okEstimate(rank: number, key: string, name: string, zoned: boolean): FaultEstimate {
  return {
    rank,
    fault_key: key,
    fault_name: name,
    status: "ok",
    reasons: [],
    parts: { low: 185, high: 185 },
    consumables: { low: 250, high: 250 },
    labour: zoned ? { low: 300, high: 700 } : { low: 150, high: 150 },
    total: zoned ? { low: 750, high: 1150 } : { low: 600, high: 600 },
    parts_basis: "itemised",
    labour_basis: zoned ? "zone_rate" : "metro_estimate",
    inputs: [
      { kind: "part", name: "Tyre valve", low: 185, high: 185, source: "F12-B_VALVE", checked_on: "2026-10-22", verified: true, stale: false, note: "" },
      { kind: "consumable", name: "Tyre sealant", low: 250, high: 250, source: "F04-TY-02 budget line 2", checked_on: null, verified: false, stale: true, note: "" },
      zoned
        ? { kind: "labour", name: "Labour (0.5-1 h x Rs 600-700/h)", low: 300, high: 700, source: "zone_labour_rates.yaml: survey", checked_on: "2026-10-30", verified: true, stale: false, note: "" }
        : { kind: "labour", name: "Labour (Delhi NCR metro estimate)", low: 150, high: 150, source: "F04-TY-02 sheet labour (budget)", checked_on: null, verified: false, stale: true, note: "" },
    ],
    flags: { needs_check: true, stale_inputs: ["Tyre sealant"], unverified_inputs: ["Tyre sealant"] },
    last_updated: "2026-10-22",
    oldest_input: "2026-10-22",
  };
}

/** Estimates for the fake session's three causes; a zone or a known pincode switches labour to the zone rate. */
export function estimates(url: URL): Estimates {
  const zoneParam = url.searchParams.get("zone") as keyof typeof ZONES | null;
  const pin = url.searchParams.get("pincode");
  const code = zoneParam ?? (pin ? PINCODES[pin] ?? null : null);
  const zoned = code === "gurugram" || code === "noida";
  return {
    session_id: url.searchParams.get("session_id") ?? "",
    segment: "budget",
    zone: {
      code,
      label: code ? ZONES[code] : null,
      source: zoneParam ? "zone" : pin ? "pincode" : "none",
      note: code ? `Zone: ${ZONES[code]}` : pin ? `Pincode ${pin} is not in our Delhi NCR zones: using the Delhi NCR metro estimate` : "No zone chosen",
      choices: Object.entries(ZONES).map(([c, label]) => ({ code: c as keyof typeof ZONES, label })),
    },
    estimates: [
      okEstimate(1, "F04-TY-02", "Slow/pinhole puncture", zoned),
      { ...okEstimate(2, "F04-TY-04", "Valve issue", false), status: "not_enough_data", reasons: ["No labour figure for this repair"], parts: null, consumables: null, labour: null, total: null, inputs: [], flags: null },
      okEstimate(3, "F04-TY-03", "Flat tyre", false),
    ],
    source_of_truth: "Prices come from this estimate service.",
    disclaimer: "This is an estimate based on your answers and our data.",
  };
}

/** Routes for api-mock.ts / e2e mock-api.ts (prefix match: compare before part detail). */
export const PARTS_ROUTES: [string, (url: URL) => unknown][] = [
  ["/api/estimates", estimates],
  ["/api/faults/", faultParts],
  ["/api/parts/compare", compare],
  ["/api/parts/", partDetail],
];
