// Helpers for the Overview and Quality pages (backend/app/quality).

import type { Accuracy, LlmUsage } from "@/lib/api";

/** 0.6254 -> "62.5%"; null -> "–". */
export const pct = (rate: number | null | undefined) => (rate === null || rate === undefined ? "–" : `${(rate * 100).toFixed(1)}%`);

/** A confirmed-outcome rate, or why it isn't shown. */
export function accuracyNote(a: Accuracy, min: number): string | null {
  return a.enough ? null : `Not enough data yet (${a.cases} of ${min} cases)`;
}

/** LLM spend in words: "LLM off" when the LLM layer is off (never "$0.00", which would look like it works). */
export function llmSpend(u: LlmUsage | null): string {
  if (!u) return "";
  if (!u.live) return "LLM off";
  return `$${u.cost_usd.toFixed(2)} of $${u.daily_cap_usd.toFixed(2)} a day · ${u.calls} call${u.calls === 1 ? "" : "s"}`;
}

/** Danger cases missed in an evaluation, from its safety recall. */
export function dangerText(missed: number | null, n: number | undefined): string {
  if (missed === null || !n) return "No danger cases in this run";
  return `${missed} of ${n} danger cases missed`;
}

export const REVIEW_TABS = [
  { key: "negative_feedback", label: "Negative feedback" },
  { key: "low_confidence", label: "Low confidence" },
  { key: "no_match", label: "No match" },
] as const;

export const DAY_CHOICES = [7, 30, 90] as const;
