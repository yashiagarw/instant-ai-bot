import type { Cost } from "@/lib/api";
import { rupees, shortDate } from "@/lib/format";
import { SEGMENT_LABELS } from "@/lib/vehicle";

function total(cost: Cost): string | null {
  if (cost.display === "amount" && cost.amount !== null) return rupees(cost.amount);
  if (cost.display === "range" && cost.min !== null && cost.max !== null) return `${rupees(cost.min)} – ${rupees(cost.max)}`;
  if (cost.display === "text" && cost.text) return cost.text;
  return null;
}

/** Segment cost with labour, total, repair time, the approx label and the price-check date. */
export function CostCard({ cost, repairTime }: { cost: Cost | null; repairTime: string }) {
  return (
    <section aria-labelledby="cost-heading" className="rounded-3xl border border-border bg-white p-5">
      <h2 id="cost-heading" className="text-xl font-black text-ink">
        Estimated cost
      </h2>
      {!cost && (
        <p className="mt-2 text-ink/80">
          We can&apos;t estimate the cost without your car&apos;s price range. A mechanic will quote after checking.
        </p>
      )}
      {cost && (
        <>
          <p className="mt-1 text-sm text-ink/70">For cars {SEGMENT_LABELS[cost.segment].toLowerCase()} (your segment)</p>
          <dl className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl bg-warm-white p-3">
              <dt className="text-sm font-semibold text-ink/70">Total, parts and labour</dt>
              <dd className="text-2xl font-black text-ink" data-testid="cost-total">
                {total(cost) ?? "Price after inspection"}
              </dd>
            </div>
            {(cost.labour !== null || cost.labour_text) && cost.display !== "on_inspection" && (
              <div className="rounded-2xl bg-warm-white p-3">
                <dt className="text-sm font-semibold text-ink/70">Labour</dt>
                <dd className="text-xl font-bold text-ink">{cost.labour !== null ? rupees(cost.labour) : cost.labour_text}</dd>
              </div>
            )}
            {repairTime && (
              <div className="rounded-2xl bg-warm-white p-3 sm:col-span-2">
                <dt className="text-sm font-semibold text-ink/70">Estimated repair time</dt>
                <dd className="text-ink">{repairTime}</dd>
              </div>
            )}
          </dl>
          {cost.display === "on_inspection" && cost.text && <p className="mt-2 text-ink/80">{cost.text}</p>}
          <p className="mt-3 text-sm text-ink/75">
            <span className="mr-2 rounded-full bg-ink/10 px-2 py-0.5 font-semibold text-ink">
              {cost.approx_label || "Approx."}
            </span>
            {cost.checked_on ? `Price checked ${shortDate(cost.checked_on)}` : "Price check date not recorded"}
          </p>
        </>
      )}
      {!cost && repairTime && (
        <p className="mt-3 text-ink">
          <span className="font-semibold">Estimated repair time:</span> {repairTime}
        </p>
      )}
    </section>
  );
}
