"use client";

import { useParams, useSearchParams } from "next/navigation";

import { ErrorMessage } from "@/components/error-message";
import { BrandBadge, FitBadge, PartImage } from "@/components/parts/part-bits";
import { DISCLAIMER } from "@/components/site-footer";
import { Skeleton } from "@/components/skeleton";
import { partsApi, type PartDetail, type PartPrice } from "@/lib/api";
import { rupeeRange, shortDate } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import { SEGMENT_LABELS } from "@/lib/vehicle";

export function variantFromQuery(params: URLSearchParams): number | null {
  const v = Number(params.get("variant_id"));
  return Number.isInteger(v) && v > 0 ? v : null;
}

const yesNo = (v: boolean | null, yes: string, no: string, unknown: string) => (v === null ? unknown : v ? yes : no);

export function PriceRow({ p }: { p: PartPrice }) {
  return (
    <li className="flex flex-col gap-1 rounded-2xl bg-warm-white p-3">
      <span className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-sm font-semibold text-ink/75">For cars {SEGMENT_LABELS[p.segment].toLowerCase()}</span>
        <span className="text-xl font-black text-ink tabular-nums">{rupeeRange(p.price_inr, p.price_max_inr)}</span>
      </span>
      <span className="text-sm text-ink/80">
        <span className="mr-2 rounded-full bg-ink/10 px-2 py-0.5 font-semibold text-ink">{p.approx_label}</span>
        {p.checked_on ? `Checked ${shortDate(p.checked_on)}` : "Check date not recorded"}
        {!p.model_verified && " · not checked for your model"}
      </span>
      <span className="text-sm text-ink/75">
        {yesNo(p.gst_included, "GST included", "GST extra", "GST: ask the shop")} ·{" "}
        {yesNo(p.fitting_included, "Fitting included", "Fitting extra", "Fitting: ask the shop")}
        {p.supplier && ` · ${p.supplier}`}
      </span>
    </li>
  );
}

function compatText(c: PartDetail["compatibility"][number]): string {
  const years = c.year_from || c.year_to ? ` ${c.year_from ?? ""}–${c.year_to ?? "now"}` : "";
  const fuel = c.fuel ? ` ${c.fuel}` : "";
  const confirm = c.status === "confirm_fit" ? " (confirm with your VIN)" : "";
  return `${c.make} ${c.model}${years}${fuel}${confirm}`;
}

function Detail({ part, variantId }: { part: PartDetail; variantId: number | null }) {
  return (
    <article aria-labelledby="part-name" className="flex flex-col gap-5 rounded-3xl border border-border bg-white p-5 sm:p-7">
      <div className="grid gap-5 sm:grid-cols-2">
        <PartImage part={part} />
        <div className="flex flex-col gap-3">
          <p className="text-sm font-bold tracking-wide text-orange-text uppercase">{part.part_type}</p>
          <h1 id="part-name" className="text-3xl leading-tight font-black tracking-tight text-ink">
            {part.name}
          </h1>
          <div className="flex flex-wrap gap-2">
            <BrandBadge part={part} />
          </div>
          {variantId ? (
            <FitBadge status={part.fit.status} />
          ) : (
            <p className="text-sm text-ink/75">Pick your car in a diagnosis to see whether this part fits it.</p>
          )}
          <dl className="grid gap-1 text-ink">
            {part.brand && (
              <div className="flex gap-2">
                <dt className="font-semibold">Brand:</dt>
                <dd>{part.brand.name}</dd>
              </div>
            )}
            {part.part_number && (
              <div className="flex gap-2">
                <dt className="font-semibold">Part number:</dt>
                <dd className="tabular-nums">
                  {part.part_number}
                  {part.quantity > 1 ? ` × ${part.quantity}` : ""}
                </dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      <section aria-labelledby="prices-h">
        <h2 id="prices-h" className="text-xl font-black text-ink">
          Prices
        </h2>
        {part.prices.length === 0 ? (
          <p className="mt-2 text-ink/85">Price on inspection.</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-2">
            {part.prices.map((p, i) => (
              <PriceRow key={i} p={p} />
            ))}
          </ul>
        )}
        <p className="mt-3 text-ink/85">The final price depends on the mechanic&apos;s inspection.</p>
      </section>

      <section aria-labelledby="fits-h">
        <h2 id="fits-h" className="text-xl font-black text-ink">
          Listed for
        </h2>
        {part.compatibility.length === 0 ? (
          <p className="mt-2 text-ink/85">
            Not listed for a specific model. Your mechanic checks that it fits before fitting it.
          </p>
        ) : (
          <ul className="mt-2 list-disc pl-5 text-ink/90">
            {part.compatibility.map((c, i) => (
              <li key={i}>{compatText(c)}</li>
            ))}
          </ul>
        )}
      </section>

      {part.faults.length > 0 && (
        <section aria-labelledby="used-h">
          <h2 id="used-h" className="text-xl font-black text-ink">
            Used to fix
          </h2>
          <ul className="mt-2 list-disc pl-5 text-ink/90">
            {[...new Map(part.faults.map((f) => [f.fault_key, f.name])).values()].map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </section>
      )}
      <p className="rounded-2xl bg-warm-white p-4 text-sm text-ink/80">{DISCLAIMER}</p>
    </article>
  );
}

/** /parts/[id]?variant_id= : one part with all its prices, the models it is listed for and what it fixes. */
export function PartDetailView() {
  const { id } = useParams<{ id: string }>();
  const variantId = variantFromQuery(useSearchParams());
  const partId = Number(id);
  const valid = Number.isInteger(partId) && partId > 0;
  const part = useLoad(valid ? `part:${partId}:${variantId}` : null, (signal) => partsApi.part(partId, variantId, signal));
  if (!valid) return <ErrorMessage message="We couldn't find that part." />;
  return (
    <div className="flex flex-col gap-4">
      {part.state.status === "loading" && (
        <div aria-busy="true" className="flex flex-col gap-4">
          <span role="status" className="sr-only">
            Loading the part…
          </span>
          <Skeleton className="h-96 rounded-3xl" />
        </div>
      )}
      {part.state.status === "error" && <ErrorMessage message={part.state.message} onRetry={part.retry} />}
      {part.state.status === "ready" && <Detail part={part.state.data} variantId={variantId} />}
    </div>
  );
}
