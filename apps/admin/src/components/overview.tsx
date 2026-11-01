"use client";

import Link from "next/link";
import { useCallback, type ReactNode } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { ErrorBox } from "@/components/error-box";
import { Page } from "@/components/guard";
import { useMe } from "@/components/staff-shell";
import { adminApi, type OverviewData, roleLabel } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { visibleNav } from "@/lib/nav";
import { age, statusLabel } from "@/lib/ops";
import { llmSpend } from "@/lib/quality";
import { useLoad } from "@/lib/use-load";

export function Overview() {
  const { me } = useMe();
  const items = visibleNav(me.permissions).filter((i) => i.key !== "overview");
  const showToday = me.permissions.includes("requests.read") || me.permissions.includes("quality.read");
  return (
    <Page nav="overview" intro={<>Welcome, {me.name}. You are signed in as {me.roles.map(roleLabel).join(", ")}.</>}>
      {showToday && <Today />}
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.key}>
              <Link
                href={item.href}
                className="flex min-h-24 items-start gap-3 rounded-3xl border border-border bg-white p-5 outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring"
              >
                <Icon aria-hidden="true" className="size-6 shrink-0 text-orange-text" />
                <span>
                  <span className="block text-lg font-black text-ink">{item.label}</span>
                  <span className="text-sm text-ink/75">{item.placeholder ?? "Open"}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="text-sm text-ink/70">Your session ends at {dateTime(me.session_expires_at)}, or after 30 minutes without activity.</p>
    </Page>
  );
}

function Tile({ label, value, children, testId }: { label: string; value: ReactNode; children?: ReactNode; testId?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-3xl border border-border bg-white p-4" data-testid={testId}>
      <span className="text-sm font-semibold text-ink/75">{label}</span>
      <span className="text-3xl font-black text-ink">{value}</span>
      {children}
    </div>
  );
}

/** Today (India time): requests by status and the ones nobody has taken, diagnoses, safety alerts, LLM spend. */
function Today() {
  const { state, reload } = useLoad(useCallback((s: AbortSignal) => adminApi.overview(s), []));
  return (
    <section aria-labelledby="today-h" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="today-h" className="text-2xl font-black text-ink">
          Today
        </h2>
        <Button type="button" variant="outline" className="h-11 rounded-full px-5 text-base" onClick={reload}>
          <RefreshCw aria-hidden="true" className="size-4" /> Refresh
        </Button>
      </div>
      {state.kind === "loading" && <p role="status">Loading today&apos;s numbers…</p>}
      {state.kind === "error" && <ErrorBox message={state.message} onRetry={reload} />}
      {state.kind === "ready" && <TodayNumbers data={state.data} />}
    </section>
  );
}

function TodayNumbers({ data: d }: { data: OverviewData }) {
  return (
    <>
      <p className="text-sm text-ink/75">Since midnight India time ({dateTime(d.day_start)}).</p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {d.requests && (
          <Tile label="Requests today" value={d.requests.total} testId="requests-today">
            <ul aria-label="Requests today by status" className="flex flex-wrap gap-1 text-sm">
              {Object.entries(d.requests.by_status).map(([s, n]) => (
                <li key={s} className="rounded-full bg-warm-white px-2 py-0.5 font-semibold">
                  {statusLabel(s)}: {n}
                </li>
              ))}
              {d.requests.total === 0 && <li className="text-ink/75">None yet</li>}
            </ul>
          </Tile>
        )}
        {d.requests && (
          <Tile label={`Waiting over ${d.requests.unassigned_after_minutes} min, no agent`} value={d.requests.unassigned.length} testId="unassigned-count" />
        )}
        {d.diagnoses && (
          <Tile label="Diagnoses today" value={d.diagnoses.started} testId="diagnoses-today">
            <span className="text-sm text-ink/75">
              {d.diagnoses.completed} finished · {d.diagnoses.safety_alerts.alerts} safety alert{d.diagnoses.safety_alerts.alerts === 1 ? "" : "s"}
            </span>
          </Tile>
        )}
        {d.llm && (
          <Tile label="LLM spend today" value={d.llm.live ? `$${d.llm.cost_usd.toFixed(2)}` : "LLM off"} testId="llm-today">
            <span className="text-sm text-ink/75">{d.llm.live ? llmSpend(d.llm) : "No LLM is in use (LLM_PROVIDER=none)."}</span>
          </Tile>
        )}
      </div>
      {d.requests && d.requests.unassigned.length > 0 && <Unassigned rows={d.requests.unassigned} minutes={d.requests.unassigned_after_minutes} />}
    </>
  );
}

function Unassigned({ rows, minutes }: { rows: NonNullable<OverviewData["requests"]>["unassigned"]; minutes: number }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-lg font-black text-ink">No agent after {minutes} minutes</h3>
      <ul aria-label="Unassigned requests" className="flex flex-col gap-2">
        {rows.map((r) => {
          const critical = r.safety_level === "high";
          return (
            <li key={r.id} data-testid="unassigned-row" data-critical={critical || undefined}>
              <Link
                href={`/requests/${r.id}`}
                className={cn(
                  "flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-2xl border-2 p-3 outline-none focus-visible:ring-3 focus-visible:ring-ring",
                  critical ? "border-danger bg-danger text-white" : "border-border bg-white text-ink hover:border-cta",
                )}
              >
                <span className="flex flex-wrap items-center gap-2 font-bold">
                  {critical && <TriangleAlert aria-hidden="true" className="size-5" />}
                  {r.reference}
                  {critical && <span className="rounded-full bg-white px-2 py-0.5 text-xs font-bold text-danger">Safety-critical</span>}
                  {r.urgent && !critical && <span className="rounded-full border-2 border-cta px-2 py-0.5 text-xs font-bold text-orange-text">Urgent</span>}
                </span>
                <span className={cn("text-sm", critical ? "text-white" : "text-ink/80")}>
                  waiting {age(r.age_minutes)} · {statusLabel(r.status)} · {r.area || r.pincode}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
