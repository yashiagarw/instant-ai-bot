"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { RefreshCw, Search, TriangleAlert } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { ErrorBox } from "@/components/error-box";
import { Checkbox, Select } from "@/components/form";
import { useCategories } from "@/components/mechanics/mechanics-view";
import { useMe } from "@/components/staff-shell";
import { adminApi, type QueueRow, type SafetyLevel } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { age, queueQuery, SAFETY_LABELS, STATUS_OPTIONS, statusLabel } from "@/lib/ops";
import { useLoad } from "@/lib/use-load";

const VIEWS = [
  { key: "open", label: "Open" },
  { key: "closed", label: "Closed" },
  { key: "all", label: "All" },
] as const;

/** Safety-critical (the diagnosis's red banner) and urgent markers. */
export function SafetyBadge({ level, urgent }: { level: SafetyLevel; urgent: boolean }) {
  return (
    <span className="flex flex-wrap gap-1">
      {level === "high" && (
        <span className="inline-flex items-center gap-1 rounded-full bg-danger px-2.5 py-0.5 text-xs font-bold whitespace-nowrap text-white">
          <TriangleAlert aria-hidden="true" className="size-3.5" /> Safety-critical
        </span>
      )}
      {level === "medium" && (
        <span className="rounded-full bg-amber-bg px-2.5 py-0.5 text-xs font-bold whitespace-nowrap text-amber-text">{SAFETY_LABELS.medium}</span>
      )}
      {urgent && <span className="rounded-full border-2 border-cta px-2.5 py-0.5 text-xs font-bold whitespace-nowrap text-orange-text">Urgent</span>}
    </span>
  );
}

export function RequestsQueue() {
  const { me } = useMe();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const q = useMemo(() => queueQuery(params), [params]);
  const { state, reload } = useLoad(useCallback((s: AbortSignal) => adminApi.requests(q, s), [q]));
  const categories = useCategories();
  const [search, setSearch] = useState(q.q ?? "");

  const setParam = useCallback(
    (key: string, value: string | null) => {
      const next = new URLSearchParams(params.toString());
      if (value) next.set(key, value);
      else next.delete(key);
      router.replace(`${pathname}${next.size ? `?${next.toString()}` : ""}`, { scroll: false });
    },
    [params, pathname, router],
  );

  function submitSearch(e: FormEvent) {
    e.preventDefault();
    setParam("q", search.trim() || null);
  }

  return (
    <div className="flex flex-col gap-4">
      <div role="group" aria-label="Which requests" className="flex flex-wrap gap-2">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            aria-pressed={q.view === v.key}
            onClick={() => setParam("view", v.key === "open" ? null : v.key)}
            className={cn(
              "min-h-11 rounded-full border-2 px-5 font-bold outline-none focus-visible:ring-3 focus-visible:ring-ring",
              q.view === v.key ? "border-ink bg-ink text-white" : "border-border bg-white text-ink",
            )}
          >
            {v.label}
          </button>
        ))}
      </div>
      <div className="grid gap-3 rounded-3xl border border-border bg-white p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Select
          label="Status"
          value={q.status ?? ""}
          onChange={(e) => setParam("status", e.target.value || null)}
          options={[{ value: "", label: "Any status" }, ...STATUS_OPTIONS]}
        />
        <Select
          label="Safety"
          value={q.safety ?? ""}
          onChange={(e) => setParam("safety", e.target.value || null)}
          options={[{ value: "", label: "Any" }, ...(["high", "medium", "low", "none"] as const).map((s) => ({ value: s, label: SAFETY_LABELS[s] }))]}
        />
        <Select
          label="Category"
          value={q.category ?? ""}
          onChange={(e) => setParam("category", e.target.value || null)}
          options={[{ value: "", label: "Any category" }, ...categories.list.map((c) => ({ value: c.code, label: c.name }))]}
        />
        <form role="search" onSubmit={submitSearch} className="flex flex-col gap-1">
          <label htmlFor="queue-q" className="font-semibold text-ink">
            Search
          </label>
          <span className="flex gap-2">
            <input
              id="queue-q"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Reference, name, area, pincode"
              className="h-12 min-w-0 flex-1 rounded-xl border border-input bg-white px-4 text-base text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring"
            />
            <Button type="submit" variant="outline" aria-label="Search requests" className="size-12 shrink-0 rounded-full">
              <Search aria-hidden="true" className="size-5" />
            </Button>
          </span>
        </form>
        <div className="flex flex-wrap items-center justify-between gap-2 sm:col-span-2 lg:col-span-4">
          {me.permissions.includes("requests.update") ? (
            <Checkbox label="Only mine" checked={q.mine} onChange={(e) => setParam("mine", e.target.checked ? "1" : null)} />
          ) : (
            <span />
          )}
          <Button type="button" variant="outline" className="h-11 rounded-full px-5 text-base" onClick={reload}>
            <RefreshCw aria-hidden="true" className="size-4" /> Refresh
          </Button>
        </div>
      </div>

      {state.kind === "loading" && <p role="status">Loading requests…</p>}
      {state.kind === "error" && <ErrorBox message={state.message} onRetry={reload} />}
      {state.kind === "ready" && <QueueTable rows={state.data} closed={q.view === "closed"} />}
    </div>
  );
}

function QueueTable({ rows, closed }: { rows: QueueRow[]; closed: boolean }) {
  return (
    <section aria-labelledby="queue-count" className="flex flex-col gap-2">
      <p id="queue-count" aria-live="polite" className="font-semibold text-ink">
        {rows.length === 0 ? "No requests match." : `${rows.length} request${rows.length === 1 ? "" : "s"}${closed ? ", newest first" : ""}`}
      </p>
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-border bg-white">
          <table className="w-full min-w-[56rem] text-left text-sm">
            <caption className="sr-only">Request queue</caption>
            <thead className="bg-warm-white text-ink">
              <tr>
                {["Request", "Waiting", "Status", "Customer", "Car and problem", "Area", "Agent / mechanic"].map((h) => (
                  <th key={h} scope="col" className="px-3 py-2 font-bold">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  data-testid="queue-row"
                  className={cn("border-t border-border align-top", r.safety_level === "high" && "bg-danger/5")}
                >
                  <th scope="row" className="px-3 py-2 font-normal">
                    <span className="flex flex-col gap-1">
                      <Link href={`/requests/${r.id}`} className="text-base font-bold text-orange-text underline underline-offset-4">
                        {r.reference}
                      </Link>
                      <SafetyBadge level={r.safety_level} urgent={r.urgent} />
                    </span>
                  </th>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <span className="block font-semibold">{age(r.age_minutes)}</span>
                    <span className="text-xs text-ink/75">{dateTime(r.created_at)}</span>
                  </td>
                  <td className="px-3 py-2">{statusLabel(r.status)}</td>
                  <td className="px-3 py-2">
                    <span className="block font-semibold">{r.name}</span>
                    <span className="text-ink/75">{r.phone}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="block font-semibold">{r.vehicle || "Car not given"}</span>
                    <span className="block text-ink/80">{r.category ?? "No category"}</span>
                    <span className="line-clamp-2 text-ink/75">{r.problem_summary}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="block">{r.area}</span>
                    <span className="text-ink/75">{r.pincode}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="block">{r.agent ?? "Nobody yet"}</span>
                    <span className="text-ink/75">{r.mechanic ?? "No mechanic"}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
