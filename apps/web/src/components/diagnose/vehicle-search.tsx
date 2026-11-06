"use client";

import { useId, useState } from "react";
import { Search } from "lucide-react";
import { useTranslations } from "next-intl";

import { ErrorMessage } from "@/components/error-message";
import { Skeleton } from "@/components/skeleton";
import { api, type SearchHit } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { useVehicleLabels } from "@/lib/use-vehicle-labels";
import { yearRange } from "@/lib/vehicle";
import { useDebounced } from "@/lib/use-debounced";

export const SEARCH_DEBOUNCE_MS = 300;

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; hits: SearchHit[]; yearMatched: boolean };

/** One search box over the catalogue (GET /api/vehicles/search), debounced. */
export function VehicleSearch({ onPick }: { onPick: (hit: SearchHit) => void }) {
  const t = useTranslations("diagnose");
  const labels = useVehicleLabels();
  const id = useId();
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim(), SEARCH_DEBOUNCE_MS);
  const search = useLoad(q.length >= 2 ? `search:${q}` : null, (signal) => api.search(q, signal));
  const state: State =
    q.length < 2
      ? { status: "idle" }
      : search.state.status === "ready"
        ? { status: "ready", hits: search.state.data.results, yearMatched: search.state.data.year_matched }
        : search.state;

  return (
    <div className="flex flex-col gap-3">
      <label htmlFor={id} className="text-lg font-bold text-ink">
        {t("searchLabel")}
      </label>
      <div className="relative">
        <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-5 size-5 -translate-y-1/2 text-ink/60" />
        <input
          id={id}
          type="search"
          inputMode="search"
          autoComplete="off"
          placeholder={t("searchPlaceholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-describedby={`${id}-status`}
          className="h-14 w-full rounded-full border-2 border-ink/15 bg-white pr-5 pl-13 text-lg text-ink outline-none placeholder:text-ink/65 focus-visible:border-cta focus-visible:ring-3 focus-visible:ring-ring/40"
        />
      </div>
      <p id={`${id}-status`} role="status" className="sr-only">
        {state.status === "loading" && t("searching")}
        {state.status === "ready" && (state.hits.length ? t("carsFound", { count: state.hits.length }) : t("noCarsFound"))}
      </p>

      {state.status === "loading" && (
        <div className="flex flex-col gap-2" aria-hidden="true">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}
      {state.status === "error" && <ErrorMessage message={state.message} onRetry={search.retry} />}
      {state.status === "ready" && state.hits.length === 0 && (
        <p className="rounded-2xl border border-border bg-white p-4 text-ink">
          {t("noMatch", { query: q })}
        </p>
      )}
      {state.status === "ready" && state.hits.length > 0 && (
        <>
          {!state.yearMatched && (
            <p className="text-sm text-ink/75">{t("closestYear")}</p>
          )}
          <ul className="flex flex-col gap-2" aria-label={t("searchResults")}>
            {state.hits.map((h) => (
              <li key={h.variant_id}>
                <button
                  type="button"
                  onClick={() => onPick(h)}
                  className="flex min-h-14 w-full flex-col items-start rounded-2xl border-2 border-ink/15 bg-white px-4 py-2.5 text-left outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring"
                >
                  <span className="font-bold text-ink">
                    {h.make} {h.model}
                  </span>
                  <span className="text-sm text-ink/75">
                    {h.variant} · {labels.fuel(h.fuel)} · {labels.transmission(h.transmission)} ·{" "}
                    {yearRange(h.year_from, h.year_to)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
