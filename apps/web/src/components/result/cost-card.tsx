"use client";

import { useTranslations } from "next-intl";

import { CountUp } from "@/components/motion/count-up";
import type { Cost } from "@/lib/api";
import { rupees, shortDate } from "@/lib/format";
import { useVehicleLabels } from "@/lib/use-vehicle-labels";

/** The total: amounts count up (CountUp), text from the dataset is shown as it is. */
function total(cost: Cost) {
  if (cost.display === "amount" && cost.amount !== null)
    return <CountUp values={[cost.amount]} format={([a]) => rupees(a)} />;
  if (cost.display === "range" && cost.min !== null && cost.max !== null)
    return <CountUp values={[cost.min, cost.max]} format={([lo, hi]) => `${rupees(lo)} – ${rupees(hi)}`} />;
  if (cost.display === "text" && cost.text) return <span lang="en">{cost.text}</span>;
  return null;
}

/** Segment cost with labour, total, repair time, the approx label and the price-check date. */
export function CostCard({ cost, repairTime }: { cost: Cost | null; repairTime: string }) {
  const t = useTranslations("result.estimate");
  const labels = useVehicleLabels();
  return (
    <section aria-labelledby="cost-heading" className="rounded-3xl border border-border bg-white p-5">
      <h2 id="cost-heading" className="text-xl font-black text-ink">
        {t("title")}
      </h2>
      {!cost && (
        <p className="mt-2 text-ink/80">{t("noSegment")}</p>
      )}
      {cost && (
        <>
          <p className="mt-1 text-sm text-ink/70">{t("segmentFor", { segment: labels.segment(cost.segment).toLowerCase() })}</p>
          <dl className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl bg-warm-white p-3">
              <dt className="text-sm font-semibold text-ink/70">{t("total")}</dt>
              <dd className="text-2xl font-black text-ink" data-testid="cost-total">
                {total(cost) ?? t("afterInspection")}
              </dd>
            </div>
            {(cost.labour !== null || cost.labour_text) && cost.display !== "on_inspection" && (
              <div className="rounded-2xl bg-warm-white p-3">
                <dt className="text-sm font-semibold text-ink/70">{t("labour")}</dt>
                <dd className="text-xl font-bold text-ink">{cost.labour !== null ? rupees(cost.labour) : cost.labour_text}</dd>
              </div>
            )}
            {repairTime && (
              <div className="rounded-2xl bg-warm-white p-3 sm:col-span-2">
                <dt className="text-sm font-semibold text-ink/70">{t("repairTimeTerm")}</dt>
                <dd className="text-ink">{repairTime}</dd>
              </div>
            )}
          </dl>
          {cost.display === "on_inspection" && cost.text && <p className="mt-2 text-ink/80">{cost.text}</p>}
          <p className="mt-3 text-sm text-ink/75">
            <span className="mr-2 rounded-full bg-ink/10 px-2 py-0.5 font-semibold text-ink">
              {cost.approx_label || t("approx")}
            </span>
            {cost.checked_on ? t("priceChecked", { date: shortDate(cost.checked_on) }) : t("noPriceCheck")}
          </p>
        </>
      )}
      {!cost && repairTime && (
        <p className="mt-3 text-ink">
          <span className="font-semibold">{t("repairTime")}</span> {repairTime}
        </p>
      )}
    </section>
  );
}
