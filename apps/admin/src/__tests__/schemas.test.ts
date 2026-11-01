import { describe, expect, it } from "vitest";

import { addCarSchema, faultSchema, partSchema, phraseSchema, priceSchema, questionSchema, requiresFromForm, requiresToForm, safetySchema, zoneRateSchema } from "@/lib/schemas";

const option = (label: string, notSure = false) => ({ label, not_sure: notSure, effects: [] });

describe("editor form schemas (mirror the server)", () => {
  it("accepts Hindi (Devanagari) phrases and labels", () => {
    expect(phraseSchema.safeParse({ text: "गाड़ी स्टार्ट नहीं हो रही", language: "hi", english_gloss: "" }).success).toBe(true);
    expect(phraseSchema.safeParse({ text: "a", language: "hi", english_gloss: "" }).success).toBe(false);
  });

  it("needs exactly one Not sure answer without effects, and distinct answers", () => {
    const base = { stage: 3, text: "Does it click?", status: "approved" as const };
    expect(questionSchema.safeParse({ ...base, options: [option("Yes"), option("No"), option("Not sure", true)] }).success).toBe(true);
    expect(questionSchema.safeParse({ ...base, options: [option("Yes"), option("No"), option("Maybe")] }).success).toBe(false);
    expect(questionSchema.safeParse({ ...base, options: [option("Yes"), option("yes"), option("Not sure", true)] }).success).toBe(false);
    const withEffect = { label: "Not sure", not_sure: true, effects: [{ fault: "F08-BT-01", effect: "supports" as const, strength: "weak" as const }] };
    expect(questionSchema.safeParse({ ...base, options: [option("Yes"), option("No"), withEffect] }).success).toBe(false);
  });

  it("asks to confirm a safety change", () => {
    const rule = { risk_level: "high", stop_driving_trigger: "", roadside_action: "", towing_recommendation: "", status: "approved", trigger_phrases: [] };
    expect(safetySchema.safeParse({ ...rule, understood: false }).success).toBe(false);
    expect(safetySchema.safeParse({ ...rule, understood: true }).success).toBe(true);
  });

  it("converts requirements between the form and the API", () => {
    const api: Record<string, string | string[]>[] = [{ feature: "start_stop" }, { fuel: ["petrol", "diesel"] }];
    const form = requiresToForm(api);
    expect(form).toEqual([{ field: "feature", value: "start_stop" }, { field: "fuel", value: "petrol, diesel" }]);
    expect(requiresFromForm(form)).toEqual(api);
  });

  it("checks fault and car fields like the server", () => {
    const fault = { name: "X", description: "", likely_fault: "", road_repairable: "yes", road_repairable_text: "", repair_location: "",
      towing_conditions_text: "", repair_time_text: "x".repeat(300), severity: null, safety_critical: false, requires: [], prior: null }; // prettier-ignore
    expect(faultSchema.safeParse(fault).success).toBe(false); // name too short
    expect(faultSchema.safeParse({ ...fault, name: "Weak battery" }).success).toBe(true);
    const car = { make: "Tata", model: "Curvv", body: "", year_from: 2024, year_to: 2023, fuel: "petrol", transmissions: ["mt"], price_segment: "mid", engine: "" };
    expect(addCarSchema.safeParse(car).success).toBe(false); // last year before the first
    expect(addCarSchema.safeParse({ ...car, year_to: null }).success).toBe(true);
  });
});

describe("part 2 schemas", () => {
  const price = { segment: "budget", price_inr: 1450, price_max_inr: null, supplier: "Boodmo", source_url: "", checked_on: "2026-10-30",
    verification_status: "approx", gst_included: "unknown", fitting_included: "unknown", model_verified: false, price_basis: "", note: "" }; // prettier-ignore

  it("needs a price's source and its check date, not in the future", () => {
    expect(priceSchema.safeParse(price).success).toBe(true);
    expect(priceSchema.safeParse({ ...price, supplier: "" }).success).toBe(false);
    expect(priceSchema.safeParse({ ...price, supplier: "", source_url: "https://boodmo.com/x" }).success).toBe(true);
    expect(priceSchema.safeParse({ ...price, checked_on: "" }).success).toBe(false);
    expect(priceSchema.safeParse({ ...price, checked_on: "2999-01-01" }).success).toBe(false);
    expect(priceSchema.safeParse({ ...price, price_max_inr: 1000 }).success).toBe(false);
  });

  it("needs a zone rate's source and date; ranges in order", () => {
    const rate = { rate_min_inr: 500, rate_max_inr: 700, source: "5 garages, phone survey", checked_on: "2026-10-30" };
    expect(zoneRateSchema.safeParse(rate).success).toBe(true);
    expect(zoneRateSchema.safeParse({ ...rate, source: "" }).success).toBe(false);
    expect(zoneRateSchema.safeParse({ ...rate, rate_max_inr: 400 }).success).toBe(false);
  });

  it("keeps generic parts without a part number and with a segment", () => {
    const part = { description: "Wiper blade", part_type: "Wiper", brand: "", brand_kind: "unspecified", part_number: "", quantity: 1, kind: "part", segment: null, generic: true };
    expect(partSchema.safeParse(part).success).toBe(false); // generic needs a segment
    expect(partSchema.safeParse({ ...part, segment: "budget" }).success).toBe(true);
    expect(partSchema.safeParse({ ...part, segment: "budget", part_number: "X1" }).success).toBe(false);
  });
});
