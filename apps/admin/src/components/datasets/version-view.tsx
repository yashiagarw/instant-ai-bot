"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowLeft, Check, X } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { Dialog } from "@im/ui/dialog";
import { StateBadge } from "@/components/datasets/datasets-view";
import { JobProgress, useJob } from "@/components/datasets/job-progress";
import { ErrorBox } from "@/components/error-box";
import { EditorSummaryView } from "@/components/knowledge/editor-summary";
import { useMe } from "@/components/staff-shell";
import { adminApi, type DatasetJob, type DiffRow, errorMessage, type CommonStats, type Comparison, type VersionDetail } from "@/lib/api";
import { isActive, missed, pct, points, searchModelLabel, versionTitle } from "@/lib/datasets";
import { dateTime } from "@/lib/format";

const MIN_REASON = 15;

function Card({ title, children, id }: { title: string; children: ReactNode; id: string }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-4 sm:p-5">
      <h2 id={id} className="text-2xl font-black text-ink">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** One dataset version: validation report, diff, evaluation, publish / override, discard, rebuild, roll back. */
export function VersionView({ id }: { id: number }) {
  const { me } = useMe();
  const canManage = me.permissions.includes("datasets.manage");
  const [state, setState] = useState<{ kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; v: VersionDetail }>({
    kind: "loading",
  });
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((a) => a + 1), []);
  useEffect(() => {
    const ctrl = new AbortController();
    adminApi
      .datasetVersion(id, ctrl.signal)
      .then((v) => setState({ kind: "ready", v }))
      .catch((e) => !ctrl.signal.aborted && setState({ kind: "error", message: errorMessage(e) }));
    return () => ctrl.abort();
  }, [id, attempt]);

  const v = state.kind === "ready" ? state.v : null;
  const running = v?.jobs.find((j) => isActive(j)) ?? null;
  const [job, setJob] = useJob(running ?? v?.jobs[0] ?? null, reload);
  const busy = isActive(job);

  if (state.kind === "loading") return <p role="status">Loading the version…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const ver = state.v;
  const draft = ver.status === "draft" || ver.status === "validated";
  const started = (j: DatasetJob) => {
    setJob(j);
    reload();
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Link href="/datasets" className="inline-flex min-h-11 items-center gap-1 self-start font-bold text-orange-text underline underline-offset-4">
          <ArrowLeft aria-hidden="true" className="size-4" /> All versions
        </Link>
        <h1 className="flex flex-wrap items-center gap-3 text-3xl font-black tracking-tight text-ink sm:text-4xl">
          {versionTitle(ver)} <StateBadge v={ver} />
        </h1>
        <p className="text-ink/80">
          {ver.upload_name && <>File {ver.upload_name} · </>}
          {ver.origin === "import" ? "Imported" : "Uploaded"} {dateTime(ver.created_at)}
          {ver.created_by && <> by {ver.created_by}</>}
          {ver.base_version_id && <> · built on v{ver.base_version_id}</>}
          {ver.published_at && <> · published {dateTime(ver.published_at)} by {ver.published_by}</>}
          {ver.archived_at && <> · archived {dateTime(ver.archived_at)}</>}
          {" "}· search model {searchModelLabel(ver.embedding_model)}
        </p>
        {ver.override_reason && (
          <p className="rounded-2xl bg-amber-bg p-3 text-amber-text">
            <strong>Published over a blocked eval.</strong> Reason: {ver.override_reason}
          </p>
        )}
      </div>

      {job && (isActive(job) || job.status === "failed") && <JobProgress job={job} canCancel={canManage} onCancelled={reload} />}

      {ver.stale && (
        <div className="flex flex-col items-start gap-3 rounded-3xl border border-border bg-amber-bg p-4 text-amber-text">
          <p>
            <strong>Out of date:</strong> another version was published after this draft was built. Rebuild it on the live version
            (same file; the eval runs again).
          </p>
          {canManage && <ActionButton label="Rebuild draft" disabled={busy} run={() => adminApi.rebuildDataset(ver.id)} onDone={started} />}
        </div>
      )}

      <Validation v={ver} canManage={canManage} busy={busy} onStarted={started} />
      {ver.editor &&
        (Object.keys(ver.editor.tables).length > 0 ||
          (ver.editor.conflicts ?? []).length > 0 ||
          (ver.editor.orphans ?? []).length > 0 ||
          (ver.editor.second_look?.count ?? 0) > 0) && (
        <Card title="Editor changes in this version" id="editor-heading">
          <EditorSummaryView summary={ver.editor} />
        </Card>
      )}
      {ver.diff.categories && <Changes v={ver} />}
      {draft && ver.status === "validated" && <Evaluation v={ver} canManage={canManage} busy={busy} onStarted={started} />}
      {ver.status === "published" || ver.status === "archived" ? (
        ver.eval.draft && <EvalTable v={ver} />
      ) : null}
      {draft && canManage && <Publish v={ver} busy={busy} onStarted={started} />}
      {draft && canManage && <Discard v={ver} busy={busy} />}
      {ver.status === "archived" && canManage && <Rollback v={ver} busy={busy} onStarted={started} />}

      {ver.jobs.length > 0 && (
        <Card title="Jobs" id="jobs-heading">
          <ul className="flex flex-col gap-2">
            {ver.jobs.map((j) => (
              <li key={j.id} className="text-ink">
                <strong>{j.kind}</strong> · {j.status} · {dateTime(j.created_at)} by {j.created_by}
                {j.error && <span className="block text-sm text-orange-text">{j.error}</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function ActionButton({
  label,
  run,
  onDone,
  disabled,
  variant,
}: {
  label: string;
  run: () => Promise<DatasetJob>;
  onDone: (j: DatasetJob) => void;
  disabled?: boolean;
  variant?: "outline";
}) {
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  return (
    <div className="flex flex-col items-start gap-2">
      <Button
        type="button"
        size={variant ? undefined : "cta"}
        variant={variant}
        className={variant ? "h-12 rounded-full px-6 text-base font-bold" : undefined}
        disabled={disabled || sending}
        onClick={() => {
          setError("");
          setSending(true);
          run()
            .then(onDone)
            .catch((e) => setError(errorMessage(e)))
            .finally(() => setSending(false));
        }}
      >
        {sending ? "Starting…" : label}
      </Button>
      {error && (
        <p role="alert" className="font-semibold text-orange-text">
          {error}
        </p>
      )}
    </div>
  );
}

function Validation({ v, canManage, busy, onStarted }: { v: VersionDetail; canManage: boolean; busy: boolean; onStarted: (j: DatasetJob) => void }) {
  const val = v.validation;
  if (v.origin === "import" && !val.checks) {
    return (
      <Card title="Validation report" id="validation-heading">
        <p className="text-ink/80">Imported with the importer CLI: its report is data/review/import-report.md.</p>
      </Card>
    );
  }
  return (
    <Card title="Validation report" id="validation-heading">
      {val.error && (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="font-semibold text-orange-text">
            The build failed: {val.error}
          </p>
          {canManage && (v.status === "draft" || v.status === "validated") && (
            <ActionButton label="Build again" disabled={busy} run={() => adminApi.rebuildDataset(v.id)} onDone={onStarted} />
          )}
        </div>
      )}
      {!val.error && !val.checks && <p className="text-ink/80">Building… the report appears when the build job finishes.</p>}
      {val.checks && (
        <ul className="flex flex-col gap-2" aria-label="Checks">
          {val.checks.map((c) => (
            <li key={c.id} className="flex items-start gap-2 text-ink" data-testid={`check-${c.id}`}>
              {c.ok ? (
                <Check aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-success" />
              ) : (
                <X aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-orange-text" />
              )}
              <span>
                <span className="sr-only">{c.ok ? "Passed: " : c.blocking ? "Failed: " : "Warning: "}</span>
                <strong>{c.label}</strong> · {c.detail}
                {!c.ok && !c.blocking && " (does not block)"}
              </span>
            </li>
          ))}
        </ul>
      )}
      {val.file_reports &&
        Object.values(val.file_reports).map((r) => (
          <div key={r.file_no} className="rounded-2xl bg-warm-white p-3 text-ink">
            <p>
              <strong>File {r.file_no}</strong>: {r.rows_read} rows read, {r.imported} imported, {r.rejected.length} rejected (header on row{" "}
              {r.header_row}).
            </p>
            {r.rejected.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-sm">
                {r.rejected.map((x, i) => (
                  <li key={i}>
                    Row {x.row} {x.id}: {x.reason}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      {val.losses && val.losses.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-lg font-bold text-ink">Would be lost compared with the live version</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-lg text-left text-sm">
              <caption className="sr-only">Losses</caption>
              <thead>
                <tr className="border-b border-border">
                  <th scope="col" className="p-2">What</th>
                  <th scope="col" className="p-2">Category</th>
                  <th scope="col" className="p-2">Fault</th>
                  <th scope="col" className="p-2">Detail</th>
                  <th scope="col" className="p-2">Live → draft</th>
                </tr>
              </thead>
              <tbody>
                {val.losses.map((x, i) => (
                  <tr key={i} className="border-b border-border">
                    <td className="p-2">{x.area}</td>
                    <td className="p-2">{x.category}</td>
                    <td className="p-2 font-mono">{x.fault_key}</td>
                    <td className="p-2">{x.detail}</td>
                    <td className="p-2">
                      {x.before} → {x.after}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {(
        [
          [val.publish_steps, "Steps that ran when it was published", "steps-published"],
          [val.steps, val.publish_steps ? "Steps that ran when the draft was built (before later edits)" : "Steps that ran", "steps-built"],
        ] as const
      ).map(
        ([run, title, id]) =>
          run && (
            <details key={id} data-testid={id} open={id === "steps-published"}>
              <summary className="min-h-11 cursor-pointer py-2 font-semibold text-orange-text">{title}</summary>
              <dl className="grid gap-1 text-sm text-ink sm:grid-cols-[max-content_1fr] sm:gap-x-4">
                {Object.entries(run.steps).map(([k, line]) => (
                  <div key={k} className="contents">
                    <dt className="font-mono font-bold">{k}</dt>
                    <dd>{line}</dd>
                  </div>
                ))}
              </dl>
            </details>
          ),
      )}
      {val.warnings && val.warnings.length > 0 && (
        <details>
          <summary className="min-h-11 cursor-pointer py-2 font-semibold text-orange-text">{val.warnings.length} notes for review</summary>
          <ul className="list-disc pl-5 text-sm text-ink">
            {val.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

function Changes({ v }: { v: VersionDetail }) {
  const rows = useMemo(
    () => [
      ...(v.diff.added ?? []).map((r) => ({ ...r, change: "Added" })),
      ...(v.diff.changed ?? []).map((r) => ({ ...r, change: "Changed" })),
      ...(v.diff.removed ?? []).map((r) => ({ ...r, change: "Removed" })),
    ],
    [v.diff],
  );
  const columns = useMemo<ColumnDef<DiffRow & { change: string }, unknown>[]>(
    () => [
      { accessorKey: "change", header: "Change" },
      { accessorKey: "fault_key", header: "Fault", cell: ({ row }) => <span className="font-mono">{row.original.fault_key}</span> },
      { accessorKey: "category", header: "Category" },
      { accessorKey: "name", header: "Name" },
      {
        id: "fields",
        header: "What changed",
        enableSorting: false,
        accessorFn: (r) => (r.fields ?? []).map((f) => f.field).join(", "),
        cell: ({ row }) =>
          row.original.fields?.length ? (
            <details>
              <summary className="min-h-11 cursor-pointer py-2 font-semibold text-orange-text">
                {row.original.fields.map((f) => f.field).join(", ")}
              </summary>
              <dl className="flex flex-col gap-2 py-1 text-sm">
                {row.original.fields.map((f) => (
                  <div key={f.field}>
                    <dt className="font-bold">{f.field}</dt>
                    <dd className="whitespace-pre-wrap">
                      <span className="text-ink/70">Before:</span> {f.before || "(empty)"}
                    </dd>
                    <dd className="whitespace-pre-wrap">
                      <span className="text-ink/70">After:</span> {f.after || "(empty)"}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          ) : (
            ""
          ),
      },
    ],
    [],
  );
  const c = v.diff_counts;
  return (
    <Card title={`Changes against v${v.base_version_id ?? "–"}`} id="diff-heading">
      <p className="text-ink" data-testid="diff-counts">
        <strong>{c.added}</strong> added · <strong>{c.changed}</strong> changed · <strong>{c.removed}</strong> removed ·{" "}
        {v.diff.unchanged ?? 0} unchanged, in {(v.diff.categories ?? []).join(", ")}
      </p>
      <DataTable
        data={rows}
        columns={columns}
        caption="Changed fault rows"
        searchLabel="Search changes"
        filters={[{ column: "change", label: "Change", options: ["Added", "Changed", "Removed"].map((x) => ({ value: x, label: x })) }]}
        pageSize={15}
        empty="No rows changed."
        getRowId={(r) => `${r.change}-${r.fault_key}`}
        csv={{
          filename: `dataset-v${v.id}-diff`,
          columns: [
            { header: "Change", value: (r) => r.change },
            { header: "Fault", value: (r) => r.fault_key },
            { header: "Category", value: (r) => r.category },
            { header: "Name", value: (r) => r.name },
            { header: "Fields", value: (r) => (r.fields ?? []).map((f) => f.field).join("; ") },
          ],
        }}
      />
    </Card>
  );
}

function EvalTable({ v }: { v: VersionDetail }) {
  const ev = v.eval;
  if (!ev.draft) return null;
  const live = ev.current;
  const cmp = ev.comparison;
  // Compared on the cases both versions have (older evals: each version's totals).
  const L: Partial<CommonStats> | undefined = cmp ? cmp.live : live?.overall;
  const D: Partial<CommonStats> = cmp ? cmp.draft : ev.draft.overall;
  const metric = (label: string, key: "top1" | "top3") => (
    <tr className="border-b border-border">
      <th scope="row" className="p-2 text-left font-semibold">
        {label}
      </th>
      <td className="p-2">{L ? pct(L[key]) : "–"}</td>
      <td className="p-2">{pct(D[key])}</td>
      <td className="p-2 font-bold">{L ? points(D[key], L[key]) : "–"}</td>
    </tr>
  );
  const safetyRow = (
    <tr className="border-b border-border" data-testid="safety-row">
      <th scope="row" className="p-2 text-left font-semibold">
        Safety recall
      </th>
      <td className="p-2">{L ? (cmp ? missed(cmp.live) : pct(L.safety_recall)) : "–"}</td>
      <td className="p-2">{cmp ? missed(cmp.draft) : pct(D.safety_recall)}</td>
      <td className="p-2 font-bold">{L ? points(D.safety_recall, L.safety_recall) : "–"}</td>
    </tr>
  );
  const gate = ev.gate;
  return (
    <div className="flex flex-col gap-3" data-testid="eval-results">
      <p className="text-ink/80">
        {ev.scope?.full ? "Full eval: every case of every category." : `Test split of ${(ev.scope?.categories ?? []).join(", ")}.`} Ran{" "}
        {ev.ran_at ? dateTime(ev.ran_at) : ""}.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-md text-left">
          <caption className="sr-only">Evaluation: live version against this draft</caption>
          <thead>
            <tr className="border-b-2 border-ink">
              <th scope="col" className="p-2">Metric</th>
              <th scope="col" className="p-2">Live {live ? `v${live.version_id}` : ""}</th>
              <th scope="col" className="p-2">This draft</th>
              <th scope="col" className="p-2">Change (points)</th>
            </tr>
          </thead>
          <tbody>
            {metric("Top-1 accuracy", "top1")}
            {metric("Top-3 accuracy", "top3")}
            {safetyRow}
            <tr className="border-b border-border">
              <th scope="row" className="p-2 text-left font-semibold">
                Cases run
              </th>
              <td className="p-2">{live?.cases ?? "–"}</td>
              <td className="p-2">{ev.draft.cases}</td>
              <td className="p-2">{cmp ? `${cmp.common} in both` : ""}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {gate && (
        <div
          data-testid="gate"
          className={cn("rounded-2xl p-3", gate.ok ? "bg-success-bg text-success" : "bg-amber-bg text-amber-text")}
        >
          <p className="font-bold">{gate.ok ? "Gate passed" : "Publishing is blocked by the eval gate"}</p>
          {gate.note && <p>{gate.note}</p>}
          {gate.reasons.length > 0 && (
            <ul className="list-disc pl-5">
              {gate.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          <p className="text-sm">Rule: top-3 may drop at most 3 points; safety recall may not drop at all.</p>
        </div>
      )}
      {cmp && <CaseDifferences cmp={cmp} live={live?.version_id} draft={v.id} />}
      {ev.draft.skipped.length > 0 && (
        <details>
          <summary className="min-h-11 cursor-pointer py-2 font-semibold text-orange-text">
            {ev.draft.skipped.length} written test cases name a fault this draft no longer has
          </summary>
          <ul className="list-disc pl-5 text-sm">
            {ev.draft.skipped.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

const OUTCOME = { fired: "alert fired", missed: "missed", absent: "case not there" } as const;

function CaseDifferences({ cmp, live, draft }: { cmp: Comparison; live?: number; draft: number }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink/80">
        Accuracy and safety recall above are measured on the {cmp.common} cases both versions have, so the numbers compare like for like.
      </p>
      {cmp.safety_changed.length > 0 && (
        <div className="flex flex-col gap-2 rounded-2xl border-2 border-danger p-3" data-testid="safety-changed">
          <h3 className="font-bold text-danger">Safety cases that changed ({cmp.safety_changed.length})</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-md text-left text-sm">
              <caption className="sr-only">Safety cases whose outcome differs between the live version and the draft</caption>
              <thead>
                <tr className="border-b border-border">
                  <th scope="col" className="p-2">Case</th>
                  <th scope="col" className="p-2">Category</th>
                  <th scope="col" className="p-2">Live v{live}</th>
                  <th scope="col" className="p-2">Draft v{draft}</th>
                </tr>
              </thead>
              <tbody>
                {cmp.safety_changed.map((c) => (
                  <tr key={c.key} className="border-b border-border">
                    <td className="p-2">{c.label}</td>
                    <td className="p-2">{c.category}</td>
                    <td className="p-2">{OUTCOME[c.live]}</td>
                    <td className="p-2 font-bold">{OUTCOME[c.draft]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {(
        [
          [cmp.only_live, `Cases only the live version has (${cmp.only_live.length})`],
          [cmp.only_draft, `Cases only this draft has (${cmp.only_draft.length})`],
        ] as const
      ).map(
        ([rows, title]) =>
          rows.length > 0 && (
            <details key={title} data-testid="only-cases">
              <summary className="min-h-11 cursor-pointer py-2 font-semibold text-orange-text">{title}</summary>
              <ul className="list-disc pl-5 text-sm">
                {rows.map((c) => (
                  <li key={c.key}>
                    {c.type} · {c.category} · {c.label}
                  </li>
                ))}
              </ul>
            </details>
          ),
      )}
    </div>
  );
}

function Evaluation({ v, canManage, busy, onStarted }: { v: VersionDetail; canManage: boolean; busy: boolean; onStarted: (j: DatasetJob) => void }) {
  const [full, setFull] = useState(false);
  return (
    <Card title="Evaluation" id="eval-heading">
      <p className="text-ink/80">
        Runs the eval harness on this draft and on the live version in the background. By default only the test split of{" "}
        {v.categories.join(", ") || "the changed categories"} (a few minutes); the full run takes much longer.
      </p>
      {canManage && (
        <div className="flex flex-col items-start gap-3">
          <label className="flex min-h-11 items-center gap-3 font-semibold text-ink">
            <input type="checkbox" checked={full} onChange={(e) => setFull(e.target.checked)} className="size-5 accent-cta" />
            Full eval (every category, every case: slow)
          </label>
          <ActionButton
            label={v.eval.draft ? "Run the evaluation again" : "Run the evaluation"}
            variant={v.eval.draft ? "outline" : undefined}
            disabled={busy}
            run={() => adminApi.evalDataset(v.id, full)}
            onDone={onStarted}
          />
        </div>
      )}
      {v.eval.draft ? <EvalTable v={v} /> : <p className="text-ink">Not run yet. Publishing needs an evaluation.</p>}
    </Card>
  );
}

function Publish({ v, busy, onStarted }: { v: VersionDetail; busy: boolean; onStarted: (j: DatasetJob) => void }) {
  const [reason, setReason] = useState("");
  const p = v.publish;
  const blocked = p.gate_reasons.length > 0;
  return (
    <Card title="Publish" id="publish-heading">
      <p className="text-ink/80">
        Publishing runs every step again (questions, merges, requirements, phrases, safety triggers, parts, photo labels, embeddings),
        checks nothing is lost, then switches the live version in one go. The current one is archived and can be rolled back to.
      </p>
      {p.blockers.length > 0 && (
        <ul className="list-disc pl-5 text-ink" data-testid="publish-blockers">
          {p.blockers.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}
      {p.blockers.length === 0 && !blocked && (
        <ActionButton label={`Publish v${v.id}`} disabled={busy} run={() => adminApi.publishDataset(v.id)} onDone={onStarted} />
      )}
      {p.blockers.length === 0 && blocked && !p.can_override && (
        <p className="rounded-2xl bg-amber-bg p-3 text-amber-text" data-testid="override-needed">
          The eval gate blocks this draft. Only a super admin can publish it anyway, with a written reason.
        </p>
      )}
      {p.blockers.length === 0 && blocked && p.can_override && (
        <div className="flex flex-col gap-3" data-testid="override">
          <label className="flex flex-col gap-1 font-semibold text-ink">
            Why publish although the gate blocks it? (written to the audit log)
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              className="rounded-xl border border-input bg-white p-3 text-base font-normal text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring"
            />
          </label>
          <p className="text-sm text-ink/75">At least {MIN_REASON} characters.</p>
          <ActionButton
            label="Override the gate and publish"
            disabled={busy || reason.trim().length < MIN_REASON}
            run={() => adminApi.publishDataset(v.id, reason.trim())}
            onDone={onStarted}
          />
        </div>
      )}
    </Card>
  );
}

function Discard({ v, busy }: { v: VersionDetail; busy: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  return (
    <section className="flex flex-col items-start gap-2">
      <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base font-bold" disabled={busy} onClick={() => setOpen(true)}>
        Discard this draft
      </Button>
      <Dialog open={open} onOpenChange={setOpen} title={`Discard v${v.id}?`} description="The draft and its report are deleted. The live version does not change.">
        <p className="text-ink">The draft and its report are deleted. The live version does not change.</p>
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            size="cta"
            onClick={() =>
              adminApi
                .discardDataset(v.id)
                .then(() => router.push("/datasets"))
                .catch((e) => setError(errorMessage(e)))
            }
          >
            Discard draft
          </Button>
          <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base" onClick={() => setOpen(false)}>
            Keep it
          </Button>
        </div>
      </Dialog>
    </section>
  );
}

function Rollback({ v, busy, onStarted }: { v: VersionDetail; busy: boolean; onStarted: (j: DatasetJob) => void }) {
  const [category, setCategory] = useState(v.category_code ?? "");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [cats, setCats] = useState<{ code: string; name: string }[]>([]);
  useEffect(() => {
    adminApi
      .datasets()
      .then((d) => setCats(d.categories))
      .catch(() => undefined);
  }, []);
  const name = cats.find((c) => c.code === category)?.name ?? category;
  return (
    <Card title="Roll back" id="rollback-heading">
      <p className="text-ink/80">
        Restores one category as it was in v{v.id}: a new version is built from the live files with that category&apos;s file taken from
        v{v.id}, checked and published. Other categories keep their current data.
      </p>
      <label className="flex flex-col gap-1 font-semibold text-ink sm:max-w-sm">
        Category to roll back
        <select
          className="h-12 rounded-xl border border-input bg-white px-4 text-base text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">Choose a category</option>
          {cats.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <div>
        <Button type="button" size="cta" disabled={busy || !category} onClick={() => setOpen(true)}>
          Roll back {category ? name : "a category"} to v{v.id}
        </Button>
      </div>
      <Dialog open={open} onOpenChange={setOpen} title={`Roll back ${name} to v${v.id}?`}>
        <p className="text-ink">
          Customers will get {name} as it was in v{v.id} as soon as the job finishes. The current live version is archived.
        </p>
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            size="cta"
            onClick={() =>
              adminApi
                .rollbackDataset(v.id, category)
                .then((j) => {
                  setOpen(false);
                  onStarted(j);
                })
                .catch((e) => setError(errorMessage(e)))
            }
          >
            Roll back
          </Button>
          <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </Dialog>
    </Card>
  );
}
