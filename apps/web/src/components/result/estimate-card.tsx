"use client";

import Link from "next/link";
import { useId } from "react";
import { useTranslations } from "next-intl";

import { CountUp } from "@/components/motion/count-up";
import { CostCard } from "@/components/result/cost-card";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import type { Cost, EstimateInput, FaultEstimate } from "@/lib/api";
import { rupeeRange, shortDate } from "@/lib/format";

const KIND = {
  part: "kindPart",
  consumable: "kindConsumable",
  labour: "kindLabour",
  service: "kindService",
} as const satisfies Record<EstimateInput["kind"], string>;

export type EstimateState = { status: "loading" } | { status: "error" } | { status: "ready"; estimate?: FaultEstimate };



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
  const t = useTranslations("result.estimate");
  const ta = useTranslations("result.area");
  const tc = useTranslations("common");
  const id = useId();
  if (state.status === "loading") {
    return (
      <section aria-label={t("title")} aria-busy="true" className="rounded-3xl border border-border bg-white p-5">
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
          {t("title")}
        </h2>
        <p className="mt-2 text-2xl font-black text-ink" data-testid="estimate-total">
          {t("onInspection")}
        </p>
        <p className="mt-1 text-ink/80">{t("notEnoughData")}</p>
        {repairTime && (
          <p className="mt-2 text-ink">
            <span className="font-semibold">{t("repairTime")}</span> {repairTime}
          </p>
        )}
        <Button asChild size="cta" className="mt-4 w-full md:w-auto">
          <Link href={`/request?session=${sessionId}`}>{tc("requestMechanic")}</Link>
        </Button>
      </section>
    );
  }

  const rows: ["parts" | "labour" | "consumables", { low: number; high: number } | null][] = [
    ["parts", e.parts],
    ["labour", e.labour],
    ["consumables", e.consumables],
  ];
  const labour = e.labour_basis === "zone_rate" && zoneLabel ? t("labourFor", { zone: zoneLabel }) : ta("metro");
  return (
    <section aria-labelledby={`${id}-h`} className="rounded-3xl border border-border bg-white p-5" data-testid="estimate">
      <h2 id={`${id}-h`} className="text-xl font-black text-ink">
        {t("title")}
      </h2>
      <p className="mt-2 text-3xl font-black text-ink tabular-nums" data-testid="estimate-total">
        <CountUp values={[e.total.low, e.total.high]} format={([low, high]) => rupeeRange(low, high)} />
      </p>
      <dl className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3" data-testid="estimate-breakdown">
        {rows
          .filter(([label, r]) => label !== "consumables" || (r && r.high > 0))
          .map(([label, r]) => (
            <div
              key={label}
              className="flex items-baseline justify-between gap-3 rounded-2xl bg-warm-white px-3 py-2 sm:flex-col sm:justify-start sm:gap-0 sm:py-3"
            >
              <dt className="text-sm font-semibold text-ink/70">{t(label)}</dt>
              <dd className="text-lg font-bold text-ink tabular-nums">{r ? rupeeRange(r.low, r.high) : "–"}</dd>
            </div>
          ))}
      </dl>
      <p className="mt-2 text-sm text-ink/75" data-testid="labour-basis">
        {labour}
      </p>
      {repairTime && (
        <p className="mt-2 text-ink">
          <span className="font-semibold">{t("repairTime")}</span> {repairTime}
        </p>
      )}
      <p className="mt-3 text-ink/85">{t("finalPrice")}</p>
      {e.inputs.length > 0 && (
        <details className="group mt-3 rounded-2xl border border-border">
          <summary className="flex min-h-11 cursor-pointer items-center rounded-2xl px-3 font-bold text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring">
            {t("sources")}
          </summary>
          <ul className="flex flex-col gap-2 border-t border-border p-3 text-sm" data-testid="estimate-sources">
            {e.inputs.map((i, n) => (
              <li key={n} className="flex flex-col gap-0.5">
                <span className="flex flex-wrap justify-between gap-x-3">
                  <span className="font-semibold text-ink">
                    {t(KIND[i.kind])}: <span lang="en">{i.name}</span>
                  </span>
                  <span className="font-bold text-ink tabular-nums">{rupeeRange(i.low, i.high)}</span>
                </span>
                <span className="text-ink/70">
                  {i.checked_on ? t("checked", { date: shortDate(i.checked_on) }) : t("noCheckDate")}
                  {" · "}
                  {i.verified ? t("checkedPrice") : t("estimateWord")} · {t("source", { source: i.source })}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
