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
