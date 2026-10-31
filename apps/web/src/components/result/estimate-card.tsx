"use client";

import Link from "next/link";
import { useId } from "react";

import { METRO_LABEL } from "@/components/result/area-picker";
import { CostCard } from "@/components/result/cost-card";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import type { Cost, EstimateInput, FaultEstimate } from "@/lib/api";
import { rupeeRange, shortDate } from "@/lib/format";

const KIND: Record<EstimateInput["kind"], string> = {
  part: "Part",
  consumable: "Consumable",
  labour: "Labour",
  service: "Service",
};

export type EstimateState = { status: "loading" } | { status: "error" } | { status: "ready"; estimate?: FaultEstimate };

function labourLabel(e: FaultEstimate, zoneLabel: string | null): string {
  if (e.labour_basis === "zone_rate" && zoneLabel) return `Labour rate for ${zoneLabel}`;
  return METRO_LABEL;
}

/** Estimated cost of one cause from GET /api/estimates: total range, parts / labour / consumables, sources and dates.
 * "Not enough data" shows "Price on inspection" with Request a Mechanic. If the estimate cannot be loaded, the
 * result's own cost (the same numbers, metro estimate) is shown instead. */
export function EstimateCard({
  state,
  fallback,
  repairTime,
  sessionId,
  zoneLabel,
  segmentKnown = true,
}: {
  state: EstimateState;
  fallback: Cost | null;
  repairTime: string;
  sessionId: string;
  zoneLabel: string | null;
  segmentKnown?: boolean;
}) {
  const id = useId();
  if (state.status === "loading") {
    return (
      <section aria-label="Estimated cost" aria-busy="true" className="rounded-3xl border border-border bg-white p-5">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="mt-3 h-20 rounded-2xl" />
      </section>
    );
  }
  // No estimate, or no price segment (unlisted car, "Not sure"): the result's own cost card explains what is missing.
  if (state.status === "error" || !state.estimate || !segmentKnown) {
    return <CostCard cost={fallback} repairTime={repairTime} />;
  }
  const e = state.estimate;

  if (e.status !== "ok" || !e.total) {
    return (
      <section aria-labelledby={`${id}-h`} className="rounded-3xl border border-border bg-white p-5" data-testid="estimate">
        <h2 id={`${id}-h`} className="text-xl font-black text-ink">
          Estimated cost
        </h2>
        <p className="mt-2 text-2xl font-black text-ink" data-testid="estimate-total">
          Price on inspection
        </p>
        <p className="mt-1 text-ink/80">
          We don&apos;t have enough price data for this repair yet. A mechanic will check the car and give you a price.
        </p>
        {repairTime && (
          <p className="mt-2 text-ink">
            <span className="font-semibold">Estimated repair time:</span> {repairTime}
          </p>
        )}
        <Button asChild size="cta" className="mt-4 w-full md:w-auto">
          <Link href={`/request?session=${sessionId}`}>Request a Mechanic</Link>
        </Button>
      </section>
    );
  }

  const rows: [string, { low: number; high: number } | null][] = [
    ["Parts", e.parts],
    ["Labour", e.labour],
    ["Consumables", e.consumables],
  ];
  return (
    <section aria-labelledby={`${id}-h`} className="rounded-3xl border border-border bg-white p-5" data-testid="estimate">
      <h2 id={`${id}-h`} className="text-xl font-black text-ink">
        Estimated cost
      </h2>
      <p className="mt-2 text-3xl font-black text-ink tabular-nums" data-testid="estimate-total">
        {rupeeRange(e.total.low, e.total.high)}
      </p>
      <dl className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3" data-testid="estimate-breakdown">
        {rows
          .filter(([label, r]) => label !== "Consumables" || (r && r.high > 0))
          .map(([label, r]) => (
            <div
              key={label}
              className="flex items-baseline justify-between gap-3 rounded-2xl bg-warm-white px-3 py-2 sm:flex-col sm:justify-start sm:gap-0 sm:py-3"
            >
              <dt className="text-sm font-semibold text-ink/70">{label}</dt>
              <dd className="text-lg font-bold text-ink tabular-nums">{r ? rupeeRange(r.low, r.high) : "–"}</dd>
            </div>
          ))}
      </dl>
      <p className="mt-2 text-sm text-ink/75" data-testid="labour-basis">
        {labourLabel(e, zoneLabel)}
      </p>
      {repairTime && (
        <p className="mt-2 text-ink">
          <span className="font-semibold">Estimated repair time:</span> {repairTime}
        </p>
      )}
      <p className="mt-3 text-ink/85">The final price depends on the mechanic&apos;s inspection.</p>
      {e.inputs.length > 0 && (
        <details className="group mt-3 rounded-2xl border border-border">
          <summary className="flex min-h-11 cursor-pointer items-center rounded-2xl px-3 font-bold text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring">
            Where these prices come from
          </summary>
          <ul className="flex flex-col gap-2 border-t border-border p-3 text-sm" data-testid="estimate-sources">
            {e.inputs.map((i, n) => (
              <li key={n} className="flex flex-col gap-0.5">
                <span className="flex flex-wrap justify-between gap-x-3">
                  <span className="font-semibold text-ink">
                    {KIND[i.kind]}: {i.name}
                  </span>
                  <span className="font-bold text-ink tabular-nums">{rupeeRange(i.low, i.high)}</span>
                </span>
                <span className="text-ink/70">
                  {i.checked_on ? `Checked ${shortDate(i.checked_on)}` : "Check date not recorded"}
                  {" · "}
                  {i.verified ? "Checked price" : "Estimate"} · Source: {i.source}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
