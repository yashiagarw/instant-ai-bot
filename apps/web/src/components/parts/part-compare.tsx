"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import { ErrorMessage } from "@/components/error-message";
import { BrandBadge, FitBadge, PartImage, partHref, PriceText } from "@/components/parts/part-bits";
import { variantFromQuery } from "@/components/parts/part-detail";
import { MAX_COMPARE } from "@/components/parts/parts-section";
import { DISCLAIMER } from "@/components/site-footer";
import { Skeleton } from "@/components/skeleton";
import { partsApi, type PartDetail } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

/** Up to MAX_COMPARE distinct, valid part ids from "?ids=12,40,7". */
export function idsFromQuery(params: URLSearchParams): number[] {
  const ids = (params.get("ids") ?? "")
    .split(",")
    .map((x) => Number(x.trim()))
    .filter((n) => Number.isInteger(n) && n > 0);
  return [...new Set(ids)].slice(0, MAX_COMPARE);
}

function latestCheck(p: PartDetail): string {
  const dates = p.prices.map((x) => x.checked_on).filter((d): d is string => !!d).sort();
  return dates.length ? shortDate(dates[dates.length - 1]) : "Not recorded";
}

function Row({ label, parts, cell }: { label: string; parts: PartDetail[]; cell: (p: PartDetail) => ReactNode }) {
  return (
    <tr className="border-t border-border align-top">
      <th scope="row" className="sticky left-0 z-10 bg-white p-3 text-left text-sm font-bold text-ink/75">
        {label}
      </th>
      {parts.map((p) => (
        <td key={p.id} className="p-3 text-ink">
          {cell(p)}
        </td>
      ))}
    </tr>
  );
}

function Table({ parts, variantId }: { parts: PartDetail[]; variantId: number | null }) {
  return (
    <div className="overflow-x-auto rounded-3xl border border-border bg-white" data-testid="compare-table">
      <table className="w-full min-w-[36rem] border-collapse">
        <caption className="sr-only">Parts compared side by side</caption>
        <thead>
          <tr>
            <td className="sticky left-0 z-10 w-28 bg-white" />
            {parts.map((p) => (
              <th key={p.id} scope="col" className="w-1/3 p-3 text-left align-top">
                <PartImage part={p} className="mb-2" />
                <Link
                  href={partHref(p.id, variantId)}
                  className="inline-flex min-h-11 items-center text-lg leading-snug font-black text-ink outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
                >
                  {p.name}
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <Row label="Price" parts={parts} cell={(p) => <PriceText prices={p.prices} className="text-lg" />} />
          <Row label="Fit" parts={parts} cell={(p) => (variantId ? <FitBadge status={p.fit.status} /> : "Pick your car to check")} />
          <Row label="Brand type" parts={parts} cell={(p) => <BrandBadge part={p} />} />
          <Row label="Brand" parts={parts} cell={(p) => p.brand?.name ?? "Any good brand"} />
          <Row
            label="Part number"
            parts={parts}
            cell={(p) => <span className="tabular-nums">{p.part_number ?? "Model specific"}</span>}
          />
          <Row label="Price checked" parts={parts} cell={latestCheck} />
          <Row
            label="Listed for"
            parts={parts}
            cell={(p) => (p.listed_for.length ? p.listed_for.join(", ") : "No specific model")}
          />
        </tbody>
      </table>
    </div>
  );
}

/** /parts/compare?ids=1,2,3&variant_id= : up to 3 parts side by side. */
export function PartCompareView() {
  const params = useSearchParams();
  const ids = idsFromQuery(params);
  const variantId = variantFromQuery(params);
  const loaded = useLoad(ids.length ? `compare:${ids.join(",")}:${variantId}` : null, (signal) =>
    partsApi.compare(ids, variantId, signal),
  );
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-3xl leading-tight font-black tracking-tight text-ink">Compare parts</h1>
      {ids.length === 0 && <ErrorMessage message="Pick up to 3 parts on your result page to compare them." />}
      {ids.length > 0 && loaded.state.status === "loading" && (
        <div aria-busy="true">
          <span role="status" className="sr-only">
            Loading the parts…
          </span>
          <Skeleton className="h-96 rounded-3xl" />
        </div>
      )}
      {loaded.state.status === "error" && <ErrorMessage message={loaded.state.message} onRetry={loaded.retry} />}
      {loaded.state.status === "ready" && (
        <>
          <Table parts={loaded.state.data.parts} variantId={variantId} />
          <p className="text-ink/85">The final price depends on the mechanic&apos;s inspection.</p>
          <p className="rounded-2xl bg-white p-4 text-sm text-ink/80">{loaded.state.data.disclaimer || DISCLAIMER}</p>
        </>
      )}
    </div>
  );
}
