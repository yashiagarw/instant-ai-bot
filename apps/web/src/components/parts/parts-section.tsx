"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { Package } from "lucide-react";

import { ErrorMessage } from "@/components/error-message";
import { PartCard } from "@/components/parts/part-bits";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { partsApi, type PriceSegment } from "@/lib/api";
import { useLoad } from "@/lib/use-load";

const SHOWN = 6;
export const MAX_COMPARE = 3;

export function compareHref(ids: number[], variantId: number | null | undefined): string {
  return `/parts/compare?ids=${ids.join(",")}${variantId ? `&variant_id=${variantId}` : ""}`;
}

/** "Parts you may need" for one cause: parts listed for the car first, then segment parts (fit not verified). */
export function PartsSection({
  faultKey,
  faultName,
  variantId,
  segment,
  lang,
}: {
  faultKey: string;
  faultName: string;
  variantId: number | null | undefined;
  segment: PriceSegment | null;
  /** "en" on the Hindi result page: this section is English only for now. */
  lang?: string;
}) {
  const id = useId();
  const [all, setAll] = useState(false);
  const [picked, setPicked] = useState<number[]>([]);
  const parts = useLoad(`parts:${faultKey}:${variantId ?? segment ?? "-"}`, (signal) =>
    partsApi.faultParts(faultKey, { variant_id: variantId, segment }, signal),
  );

  return (
    <section lang={lang} aria-labelledby={`${id}-heading`} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-5">
      <div>
        <h2 id={`${id}-heading`} className="flex items-center gap-2 text-2xl font-black text-ink">
          <Package aria-hidden="true" className="size-6 text-orange-text" />
          Parts you may need
        </h2>
        <p className="mt-1 text-sm text-ink/75">For {faultName}. The mechanic confirms the parts after checking the car.</p>
      </div>

      {parts.state.status === "loading" && (
        <div className="grid gap-3 sm:grid-cols-2" aria-busy="true">
          <span role="status" className="sr-only">
            Loading parts…
          </span>
          <Skeleton className="h-72 rounded-3xl" />
          <Skeleton className="h-72 rounded-3xl" />
        </div>
      )}
      {parts.state.status === "error" && <ErrorMessage message={parts.state.message} onRetry={parts.retry} />}
      {parts.state.status === "ready" &&
        (parts.state.data.parts.length === 0 ? (
          <p className="text-ink/85" data-testid="no-parts">
            No parts are listed for this cause yet. A mechanic will tell you what is needed after checking.
          </p>
        ) : (
          <>
            <ul className="grid gap-3 sm:grid-cols-2">
              {(all ? parts.state.data.parts : parts.state.data.parts.slice(0, SHOWN)).map((p) => (
                <li key={p.id} className="flex">
                  <div className="flex w-full">
                    <PartCard
                      part={p}
                      variantId={variantId}
                      compare={{
                        checked: picked.includes(p.id),
                        disabled: picked.length >= MAX_COMPARE,
                        onChange: (on) => setPicked((ids) => (on ? [...ids, p.id] : ids.filter((x) => x !== p.id))),
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
            {parts.state.data.parts.length > SHOWN && (
              <button
                type="button"
                onClick={() => setAll((v) => !v)}
                className="inline-flex min-h-11 items-center self-start rounded-full font-bold text-orange-text underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
              >
                {all ? "Show fewer parts" : `Show all ${parts.state.data.parts.length} parts`}
              </button>
            )}
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center" aria-live="polite">
              <p className="text-sm text-ink/75">
                {picked.length === 0
                  ? `Tick up to ${MAX_COMPARE} parts to compare them side by side.`
                  : `${picked.length} of ${MAX_COMPARE} picked to compare.`}
              </p>
              {picked.length >= 2 && (
                <Button asChild variant="outline" className="h-11 rounded-full px-5 text-base font-bold">
                  <Link href={compareHref(picked, variantId)}>Compare {picked.length} parts</Link>
                </Button>
              )}
            </div>
          </>
        ))}
    </section>
  );
}
