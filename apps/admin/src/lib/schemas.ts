// Form schemas (Zod). They mirror the server's (backend/app/knowledge/edits/handlers.py and
// backend/app/vehicles/admin_api.py): the server checks everything again. Text accepts any script (Devanagari too).

import { z } from "zod";

const text = (max = 4000) => z.string().trim().max(max, `At most ${max} characters`);
const required = (min: number, max: number, what = "This") =>
  z.string().trim().min(min, `${what} needs at least ${min} characters`).max(max, `At most ${max} characters`);

export const REQUIREMENT_FIELDS = ["feature", "fuel", "transmission"] as const;
export const FUELS = ["petrol", "diesel", "cng", "hybrid", "ev"] as const;
export const TRANSMISSIONS = ["mt", "amt", "cvt", "dct", "at"] as const;
export const SEGMENTS = ["budget", "mid", "premium"] as const;

export const faultSchema = z.object({
  name: required(2, 300, "The name"),
  description: text(),
  likely_fault: text(),
  road_repairable: z.enum(["yes", "limited", "no", "unknown"]),
  road_repairable_text: text(),
  repair_location: text(),
  towing_conditions_text: text(),
  repair_time_text: text(),
  severity: z.enum(["low", "medium", "high"]).nullable(),
  safety_critical: z.boolean(),
  requires: z.array(z.object({ field: z.enum(REQUIREMENT_FIELDS), value: z.string().trim().min(1, "Give a value") })),
  prior: z.number({ invalid_type_error: "A number" }).gt(0, "More than 0").max(1000).nullable(),
});
export type FaultForm = z.infer<typeof faultSchema>;

export const newFaultSchema = z.object({
  name: required(2, 300, "The name"),
  category_code: z.string().min(1, "Choose a category"),
  description: text(),
});

export const linesSchema = z.object({
  lines: z.array(z.object({ text: required(1, 2000, "A line") })).max(60, "At most 60 lines"),
});

export const phraseSchema = z.object({
  text: required(2, 300, "The phrase"),
  language: z.enum(["en", "hinglish", "hi"]),
  english_gloss: text(300),
});

const effectSchema = z.object({
  fault: z.string().min(1, "Choose a fault"),
  effect: z.enum(["supports", "rules_out"]),
  strength: z.enum(["strong", "moderate", "weak"]),
});

export const questionSchema = z
  .object({
    stage: z.number().int().min(2).max(9),
    text: required(3, 400, "The question"),
    status: z.enum(["approved", "draft", "rejected"]),
    options: z
      .array(z.object({ label: required(1, 200, "An answer"), not_sure: z.boolean(), effects: z.array(effectSchema) }))
      .min(3, "At least two answers plus Not sure")
      .max(20, "At most 20 answers"),
  })
  .superRefine((q, ctx) => {
    const notSure = q.options.filter((o) => o.not_sure);
    if (notSure.length !== 1 || notSure[0].effects.length) {
      ctx.addIssue({ code: "custom", path: ["options"], message: "Exactly one Not sure answer, with no effects" });
    }
    const labels = q.options.map((o) => o.label.trim().toLowerCase());
    if (new Set(labels).size !== labels.length) ctx.addIssue({ code: "custom", path: ["options"], message: "Two answers have the same label" });
  });
export type QuestionForm = z.infer<typeof questionSchema>;

export const safetySchema = z.object({
  risk_level: z.enum(["low", "medium", "high"]),
  stop_driving_trigger: text(),
  roadside_action: text(),
  towing_recommendation: text(),
  status: z.enum(["draft", "active_pending_signoff", "approved", "rejected"]),
  trigger_phrases: z.array(z.object({ text: required(2, 120, "A phrase") })),
  understood: z.literal(true, { errorMap: () => ({ message: "Confirm that you checked this safety change" }) }),
});
export type SafetyForm = z.infer<typeof safetySchema>;

const nullableNumber = (min: number, max: number, int = false) => {
  const n = int ? z.number().int() : z.number();
  return n.min(min).max(max).nullable();
};

export const categorySchema = z.object({
  name: required(2, 120, "The name"),
  kind: z.enum(["diagnose", "fast_track", "inspect"]),
  beta: z.boolean(),
  wave: z.number().min(0).max(9),
  filters: z.array(z.string()),
  config: z.object({
    question_budget: nullableNumber(1, 12, true),
    stop_probability: nullableNumber(0.01, 1),
    stop_margin: nullableNumber(0, 1),
    min_questions: nullableNumber(0, 8, true),
  }),
});
export type CategoryForm = z.infer<typeof categorySchema>;

export const groupSchema = z.object({
  code: z.string().trim().regex(/^[a-z][a-z0-9_]{1,40}$/, "Lower-case letters, digits and _ (e.g. car_fire)"),
  group_type: z.enum(["tile", "emergency", "inspection"]),
  label_en: required(2, 80, "The English label"),
  label_hi: required(1, 80, "The Hindi label"),
  hi_reviewed: z.boolean(),
  categories: z.array(z.string()),
  position: z.number().int().min(0).max(99),
});
export type GroupForm = z.infer<typeof groupSchema>;

export const filterSchema = z
  .object({
    name: z.string().trim().regex(/^[a-z][a-z0-9_]{1,40}$/, "Lower-case letters, digits and _"),
    fuel: z.array(z.enum(FUELS)),
    transmission: z.array(z.enum(TRANSMISSIONS)),
  })
  .refine((f) => f.fuel.length || f.transmission.length, { message: "Choose at least one fuel or gearbox", path: ["fuel"] });

const thisYear = new Date().getFullYear();
export const addCarSchema = z
  .object({
    make: required(2, 60, "The make"),
    model: required(1, 60, "The model"),
    body: text(40),
    year_from: z.number({ invalid_type_error: "A year" }).int().min(1990).max(thisYear + 1),
    year_to: z.number().int().min(1990).max(thisYear + 1).nullable(),
    fuel: z.enum(FUELS),
    transmissions: z.array(z.enum(TRANSMISSIONS)).min(1, "Choose at least one gearbox"),
    price_segment: z.enum(SEGMENTS),
    engine: text(40),
  })
  .refine((c) => c.year_to === null || c.year_to >= c.year_from, { message: "The last year is before the first", path: ["year_to"] });
export type AddCarForm = z.infer<typeof addCarSchema>;

export const generatedSchema = z.object({
  category: z.string().min(1, "Choose the category"),
  stage: z.number().int().min(2).max(9),
  text: required(3, 400, "The question"),
  options: z.array(z.object({ label: required(1, 200, "An answer") })).min(2, "At least two answers"),
});
export type GeneratedForm = z.infer<typeof generatedSchema>;

/** [{feature: "start_stop"}, {fuel: ["diesel"]}] <-> [{field, value: "start_stop"}, {field: "fuel", value: "diesel"}]. */
export function requiresToForm(requires: Record<string, string | string[]>[]): FaultForm["requires"] {
  return requires.map((r) => {
    const [field, value] = Object.entries(r)[0];
    return { field: field as (typeof REQUIREMENT_FIELDS)[number], value: Array.isArray(value) ? value.join(", ") : String(value) };
  });
}

export function requiresFromForm(rows: FaultForm["requires"]): Record<string, string | string[]>[] {
  return rows.map(({ field, value }) =>
    field === "feature" ? { feature: value.trim() } : { [field]: value.split(",").map((v) => v.trim()).filter(Boolean) },
  );
}

// ---------------------------------------------------------------- part 2: vehicles, parts, prices, labour

export const SECOND_LOOK_INR = 20000;
const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Give the date it was checked")
  .refine((d) => d <= new Date().toISOString().slice(0, 10), "The check date is in the future");
const money = (max: number) => z.number({ invalid_type_error: "An amount in rupees" }).int("Whole rupees").min(0).max(max);

export const makeSchema = z.object({ name: required(2, 60, "The name"), aliases: text(300) });
export const modelSchema = z.object({ name: required(1, 60, "The name"), body_type: text(40), aliases: text(300) });
const years = { year_from: z.number({ invalid_type_error: "A year" }).int().min(1980).max(2100), year_to: z.number().int().min(1980).max(2100).nullable() };
export const generationSchema = z
  .object({ name: required(1, 80, "The name"), ...years })
  .refine((g) => g.year_to === null || g.year_to >= g.year_from, { message: "The last year is before the first", path: ["year_to"] });
export const variantSchema = z
  .object({
    generation_id: z.number().nullable(),
    fuel: z.enum(FUELS),
    transmission: z.enum(TRANSMISSIONS),
    engine: text(40),
    ...years,
    price_segment: z.enum(SEGMENTS),
    features: z.record(z.enum(["yes", "no", "unknown"])),
  })
  .refine((g) => g.year_to === null || g.year_to >= g.year_from, { message: "The last year is before the first", path: ["year_to"] });
export type VariantForm = z.infer<typeof variantSchema>;

export const partSchema = z
  .object({
    description: required(2, 300, "The description"),
    part_type: required(2, 120, "The part type"),
    brand: text(120),
    brand_kind: z.enum(["oem", "oes", "aftermarket", "unspecified"]),
    part_number: text(80),
    quantity: z.number().int().min(1).max(50),
    kind: z.enum(["part", "consumable"]),
    segment: z.enum(SEGMENTS).nullable(),
    generic: z.boolean(),
  })
  .refine((p) => !p.generic || !p.part_number, { message: "A generic part has no part number", path: ["part_number"] })
  .refine((p) => !p.generic || p.segment, { message: "A generic part needs its price segment", path: ["segment"] });
export type PartForm = z.infer<typeof partSchema>;

export const priceSchema = z
  .object({
    segment: z.enum(SEGMENTS),
    price_inr: money(10_000_000),
    price_max_inr: money(10_000_000).nullable(),
    supplier: text(500),
    source_url: text(500),
    checked_on: isoDate,
    verification_status: z.enum(["checked", "listed_recheck", "approx"]),
    gst_included: z.enum(["yes", "no", "unknown"]),
    fitting_included: z.enum(["yes", "no", "unknown"]),
    model_verified: z.boolean(),
    price_basis: text(200),
    note: text(1000),
  })
  .refine((p) => p.supplier || p.source_url, { message: "A price needs its source: the supplier or a link", path: ["supplier"] })
  .refine((p) => p.price_max_inr === null || p.price_max_inr >= p.price_inr, { message: "The highest price is below the lowest", path: ["price_max_inr"] });
export type PriceForm = z.infer<typeof priceSchema>;

export const fitSchema = z
  .object({
    model_id: z.number({ invalid_type_error: "Choose the car" }).int().positive("Choose the car"),
    year_from: z.number().int().min(1980).max(2100).nullable(),
    year_to: z.number().int().min(1980).max(2100).nullable(),
    fuel: z.enum(FUELS).nullable(),
    transmission: z.enum(TRANSMISSIONS).nullable(),
    verification_status: z.enum(["listed", "confirm_fit"]),
    fit_text: required(2, 300, "Say what the source says"),
    source_url: text(500),
  })
  .refine((f) => !f.year_from || !f.year_to || f.year_to >= f.year_from, { message: "The last year is before the first", path: ["year_to"] });
export type FitForm = z.infer<typeof fitSchema>;

export const zoneRateSchema = z
  .object({ rate_min_inr: money(100_000).min(1, "More than 0"), rate_max_inr: money(100_000).min(1, "More than 0"), source: required(3, 500, "The source"), checked_on: isoDate })
  .refine((r) => r.rate_max_inr >= r.rate_min_inr, { message: "The highest rate is below the lowest", path: ["rate_max_inr"] });
export type ZoneRateForm = z.infer<typeof zoneRateSchema>;

export const labourSchema = z.object({
  repair: required(2, 200, "The repair"),
  segment: z.enum(SEGMENTS),
  city: required(2, 80, "The city"),
  amount_inr: money(1_000_000).min(1, "More than 0"),
  workshop_type: text(120),
  basis: required(3, 500, "The source (who quoted it, where)"),
  status: z.enum(["approx", "listed"]),
  checked_on: isoDate,
});
export type LabourForm = z.infer<typeof labourSchema>;

export const triState = (v: boolean | null) => (v === true ? "yes" : v === false ? "no" : "unknown");
export const fromTriState = (v: "yes" | "no" | "unknown") => (v === "yes" ? true : v === "no" ? false : null);

// ---------------------------------------------------------------- mechanics (backend/app/mechanics/admin_api.py)

/** An Indian mobile number: 10 digits starting 6-9, optionally with +91 (the server stores +91XXXXXXXXXX). */
export const isMobile = (v: string) => /^(?:\+?91)?[6-9]\d{9}$/.test(v.replace(/[\s-]/g, ""));

export const mechanicSchema = z.object({
  name: required(2, 80, "The name"),
  phone: z.string().trim().refine(isMobile, "A 10-digit Indian mobile number"),
  base_pincode: z.string().trim().regex(/^\d{6}$/, "A pincode has 6 digits"),
  base_area: text(120),
  rating: z.number({ invalid_type_error: "A number" }).min(0, "0 to 5").max(5, "0 to 5").nullable(),
  max_jobs_per_day: z.number({ invalid_type_error: "A number" }).int("A whole number").min(1, "1 to 30").max(30, "1 to 30"),
  active: z.boolean(),
  notes: text(1000),
});
export type MechanicForm = z.infer<typeof mechanicSchema>;
