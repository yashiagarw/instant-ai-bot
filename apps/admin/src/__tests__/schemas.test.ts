import { describe, expect, it } from "vitest";

import { addCarSchema, faultSchema, phraseSchema, questionSchema, requiresFromForm, requiresToForm, safetySchema } from "@/lib/schemas";

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
