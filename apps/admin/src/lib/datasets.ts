// Display helpers for the Datasets page.

import type { DatasetJob, DatasetVersion } from "@/lib/api";

/** What a version is, in a word or two, for the status badge. */
export function versionState(v: DatasetVersion): { label: string; tone: "live" | "ok" | "attention" | "muted" } {
  if (v.status === "published") return { label: "Live", tone: "live" };
  if (v.status === "archived") return { label: "Archived", tone: "muted" };
  if (v.build_error) return { label: "Build failed", tone: "attention" };
  if (v.validated === null) return { label: "Building", tone: "muted" };
  if (v.stale) return { label: "Out of date", tone: "attention" };
  if (v.status === "validated") return { label: "Validated", tone: "ok" };
  return { label: "Needs fixes", tone: "attention" };
}

export function versionTitle(v: Pick<DatasetVersion, "id" | "origin" | "categories" | "rollback_of_id">): string {
  const what = v.categories.length ? v.categories.join(", ") : "all categories";
  if (v.origin === "rollback") return `v${v.id} · ${what} rolled back to v${v.rollback_of_id}`;
  if (v.origin === "import") return `v${v.id} · import of every file`;
  return `v${v.id} · ${what}`;
}

/** 0.98864 -> "98.86%"; null -> "–". */
export function pct(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? "–" : `${(rate * 100).toFixed(2)}%`;
}

/** Change in points between two rates: "+1.50", "-3.20", "0.00" (draft minus live). */
export function points(draft: number | null | undefined, live: number | null | undefined): string {
  if (draft === null || draft === undefined || live === null || live === undefined) return "–";
  const d = Math.round((draft - live) * 10000) / 100;
  return `${d > 0 ? "+" : ""}${d.toFixed(2)}`;
}

/** "2 of 176 danger cases missed (98.86%)". */
export function missed(s: { safety_n: number; safety_missed: number; safety_recall: number | null }): string {
  if (!s.safety_n) return "no danger cases";
  return `${s.safety_missed} of ${s.safety_n} danger cases missed (${pct(s.safety_recall)})`;
}

export const JOB_KIND: Record<DatasetJob["kind"], string> = {
  build: "Building the draft",
  eval: "Running the evaluation",
  publish: "Publishing",
  rollback: "Rolling back",
};

export const isActive = (j: DatasetJob | null | undefined) => !!j && (j.status === "queued" || j.status === "running");

/** Seconds a job has waited for the worker (to suggest starting it). */
export function waitingSeconds(j: DatasetJob, now = Date.now()): number {
  return j.status === "queued" ? Math.max(0, Math.round((now - new Date(j.created_at).getTime()) / 1000)) : 0;
}
