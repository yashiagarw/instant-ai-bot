"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useId, type ReactNode } from "react";
import { TriangleAlert } from "lucide-react";

import { cn } from "@im/ui/cn";
import { ErrorBox } from "@/components/error-box";
import { adminApi, type Accuracy, type EvalStatsRow, type QualityData, type ReviewKind } from "@/lib/api";
import { date, dateTime } from "@/lib/format";
import { accuracyNote, DAY_CHOICES, dangerText, pct, REVIEW_TABS } from "@/lib/quality";
import { useLoad } from "@/lib/use-load";

export function QualityView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const days = DAY_CHOICES.find((d) => String(d) === params.get("days")) ?? 30;
  const tab = REVIEW_TABS.find((t) => t.key === params.get("review"))?.key ?? "negative_feedback";
  const { state, reload } = useLoad(useCallback((s: AbortSignal) => adminApi.quality(days, s), [days]));

  const set = (key: string, value: string) => {
    const q = new URLSearchParams(params.toString());
    q.set(key, value);
    router.replace(`${pathname}?${q.toString()}`, { scroll: false });
  };

  return (
    <div className="flex flex-col gap-6">
      <div role="group" aria-label="Period" className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-ink">Period:</span>
        {DAY_CHOICES.map((d) => (
          <button
            key={d}
            type="button"
            aria-pressed={days === d}
            onClick={() => set("days", String(d))}
            className={cn(
              "min-h-11 rounded-full border-2 px-4 font-bold outline-none focus-visible:ring-3 focus-visible:ring-ring",
              days === d ? "border-ink bg-ink text-white" : "border-border bg-white text-ink",
            )}
          >
            Last {d} days
          </button>
        ))}
      </div>
      {state.kind === "loading" && <p role="status">Loading quality numbers…</p>}
      {state.kind === "error" && <ErrorBox message={state.message} onRetry={reload} />}
      {state.kind === "ready" && <Metrics q={state.data} />}
      <ReviewLists tab={tab} days={days} onTab={(k) => set("review", k)} />
    </div>
  );
}

function Card({ title, children, intro, className }: { title: string; children: ReactNode; intro?: ReactNode; className?: string }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={cn("flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:p-6", className)}>
      <div className="flex flex-col gap-1">
        <h2 id={id} className="text-xl font-black text-ink">
          {title}
        </h2>
        {intro && <div className="text-sm text-ink/80">{intro}</div>}
      </div>
      {children}
    </section>
  );
}

function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="flex flex-col rounded-2xl bg-warm-white p-3">
      <dt className="text-sm font-semibold text-ink/75">{label}</dt>
      <dd className="text-2xl font-black text-ink">{value}</dd>
      {note && <dd className="text-sm text-ink/75">{note}</dd>}
    </div>
  );
}

function Table({ caption, head, rows }: { caption: string; head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-border">
      <table className="w-full min-w-[28rem] text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-warm-white">
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-bold text-ink">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border">
              {r.map((c, j) =>
                j === 0 ? (
                  <th key={j} scope="row" className="px-3 py-2 font-semibold text-ink">
                    {c}
                  </th>
                ) : (
                  <td key={j} className="px-3 py-2 text-ink">
                    {c}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const evalRow = (label: ReactNode, s: EvalStatsRow) => [label, s.ranked_n ?? s.n ?? 0, pct(s.top1), pct(s.top3), s.safety_n ? pct(s.safety_recall) : "–"];

function accuracyCells(a: Accuracy, min: number) {
  const note = accuracyNote(a, min);
  return note ? [a.cases, <span key="n" className="text-ink/75">{note}</span>, ""] : [a.cases, pct(a.top1), pct(a.top3)];
}

function Metrics({ q }: { q: QualityData }) {
  const e = q.eval;
  const min = q.confirmed.min_cases;
  const missed = e?.danger_missed ?? null;
  return (
    <>
      <Card title="Safety" intro="Danger cases: a case where the app must show a stop-driving warning.">
        <dl className="grid gap-3 sm:grid-cols-2">
          <div className={cn("flex flex-col rounded-2xl p-3", missed ? "bg-danger text-white" : "bg-warm-white text-ink")} data-testid="danger-missed">
            <dt className={cn("flex items-center gap-1 text-sm font-semibold", missed ? "text-white" : "text-ink/75")}>
              {missed ? <TriangleAlert aria-hidden="true" className="size-4" /> : null}
              Danger cases missed (latest evaluation)
            </dt>
            <dd className="text-2xl font-black">{e ? (missed ?? "–") : "No evaluation yet"}</dd>
            {e && <dd className="text-sm">{dangerText(missed, e.overall.safety_n)}</dd>}
          </div>
          <Stat
            label="Safety alerts shown today"
            value={q.safety.alerts_today.alerts}
            note={
              Object.entries(q.safety.alerts_today.by_risk)
                .map(([r, n]) => `${r}: ${n}`)
                .join(" · ") || `${q.safety.alerts_today.sessions} sessions`
            }
          />
        </dl>
      </Card>

      <Card
        title="Latest evaluation"
        intro={
          e ? (
            <>
              Live dataset version {e.version_id}, run {dateTime(e.ran_at)} ({e.scope?.full ? "all cases" : `${e.scope?.split ?? "test"} split`}
              {e.scope?.categories?.length ? `, ${e.scope.categories.join(", ")}` : ""}). Synthetic and dataset cases only: real cases are below, never mixed in.
            </>
          ) : (
            "The live version has not been evaluated yet. Run an evaluation on the Datasets page."
          )
        }
      >
        {e && (
          <>
            <Table caption="Evaluation by category" head={["Category", "Cases", "Top-1", "Top-3", "Safety recall"]} rows={[evalRow("All", e.overall), ...e.by_category.map((c) => evalRow(c.name, c))]} />
            <h3 className="text-lg font-black text-ink">Real cases</h3>
            {e.real ? (
              <>
                <Table caption="Real cases by category" head={["Category", "Cases", "Top-1", "Top-3", "Safety recall"]} rows={[evalRow("All real cases", e.real.overall), ...e.real.by_category.map((c) => evalRow(c.name, c))]} />
                {e.real.skipped.length > 0 && <p className="text-sm text-amber-text">{e.real.skipped.length} real cases could not run on this version.</p>}
              </>
            ) : (
              <p className="text-ink/80" data-testid="no-real-cases">
                No real cases yet. Add one from a session below (&quot;Add to golden set&quot;).
              </p>
            )}
          </>
        )}
      </Card>

      <Card
        title="Confirmed by mechanics"
        intro={`How often the app's top cause (top-1) or one of its top 3 was the fault the mechanic confirmed on a completed job. All time; rates show from ${min} cases.`}
      >
        <dl className="grid gap-3 sm:grid-cols-3">
          <Stat label="Confirmed jobs" value={q.confirmed.overall.cases} note={`${q.confirmed_window.cases} in the last ${q.days} days`} />
          <Stat label="Top-1" value={q.confirmed.overall.enough ? pct(q.confirmed.overall.top1) : "–"} note={accuracyNote(q.confirmed.overall, min)} />
          <Stat label="Top-3" value={q.confirmed.overall.enough ? pct(q.confirmed.overall.top3) : "–"} />
        </dl>
        {q.confirmed.by_category.length > 0 && (
          <Table caption="Confirmed accuracy by category" head={["Category", "Cases", "Top-1", "Top-3"]} rows={q.confirmed.by_category.map((c) => [c.name, ...accuracyCells(c, min)])} />
        )}
        {q.confirmed.by_version.length > 0 && (
          <Table
            caption="Confirmed accuracy by dataset version"
            head={["Dataset version", "Cases", "Top-1", "Top-3"]}
            rows={q.confirmed.by_version.map((v) => [v.dataset_version_id === null ? "Unknown" : `Version ${v.dataset_version_id}`, ...accuracyCells(v, min)])}
          />
        )}
      </Card>

      <Card title={`Diagnoses (last ${q.days} days)`} intro={`Since ${date(q.since)}, India time.`}>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Finished diagnoses" value={q.sessions.completed} />
          <Stat label="Low confidence" value={pct(q.sessions.low_confidence_rate)} note={`${q.sessions.low_confidence} of ${q.sessions.with_result} with a result`} />
          <Stat label="No match" value={q.sessions.no_match} note={pct(q.sessions.no_match_rate)} />
          <Stat label="Average questions" value={q.sessions.avg_questions ?? "–"} />
          <Stat label="Helpful" value={pct(q.helpful.rate)} note={`${q.helpful.helpful} of ${q.helpful.answers} customer answers`} />
          <Stat label="LLM failures" value={q.llm.live ? `${q.llm.failures}` : "LLM off"} note={q.llm.live ? pct(q.llm.failure_rate) : undefined} />
          <Stat label="LLM fallback rate" value={q.llm.live ? pct(q.llm.fallback_rate) : "LLM off"} note={q.llm.live ? `${q.llm.fallbacks} of ${q.llm.calls} calls` : undefined} />
        </dl>
      </Card>
    </>
  );
}

function ReviewLists({ tab, days, onTab }: { tab: ReviewKind; days: number; onTab: (k: ReviewKind) => void }) {
  const { state, reload } = useLoad(useCallback((s: AbortSignal) => adminApi.reviewList(tab, days, s), [tab, days]));
  return (
    <Card title="Sessions to review" intro="Open one to see its questions and answers, read-only. Phone numbers are hidden.">
      <div role="tablist" aria-label="Sessions to review" className="flex flex-wrap gap-2">
        {REVIEW_TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            type="button"
            id={`review-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls="review-panel"
            onClick={() => onTab(t.key)}
            className={cn(
              "min-h-11 rounded-full border-2 px-4 font-bold outline-none focus-visible:ring-3 focus-visible:ring-ring",
              tab === t.key ? "border-ink bg-ink text-white" : "border-border bg-white text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="review-panel" aria-labelledby={`review-${tab}`}>
        {state.kind === "loading" && <p role="status">Loading…</p>}
        {state.kind === "error" && <ErrorBox message={state.message} onRetry={reload} />}
        {state.kind === "ready" &&
          (state.data.length === 0 ? (
            <p className="text-ink/80">Nothing in the last {days} days.</p>
          ) : (
            <ul aria-label="Review list" className="flex flex-col gap-2">
              {state.data.map((r) => (
                <li key={r.session_id} className="flex flex-col gap-1 rounded-2xl border border-border p-3" data-testid="review-row">
                  <span className="flex flex-wrap items-center justify-between gap-2">
                    <Link href={`/quality/sessions/${r.session_id}`} className="font-bold text-orange-text underline underline-offset-4">
                      {r.vehicle} · {dateTime(r.at)}
                    </Link>
                    {r.golden && <span className="rounded-full bg-success-bg px-2 py-0.5 text-xs font-bold text-success">In golden set</span>}
                  </span>
                  {r.text && <span className="text-ink">&ldquo;{r.text}&rdquo;</span>}
                  {r.comment && <span className="text-ink">Feedback: {r.comment}</span>}
                  <span className="text-sm text-ink/75">
                    {r.top ? `Top cause: ${r.top.name ?? r.top.fault_key} (${r.top.confidence} confidence)` : "No cause found"}
                    {r.topic ? ` · ${r.topic}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ))}
      </div>
    </Card>
  );
}
