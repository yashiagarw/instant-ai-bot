"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Upload } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { JobProgress, useJob } from "@/components/datasets/job-progress";
import { ErrorBox } from "@/components/error-box";
import { adminApi, type DatasetJob, type DatasetsOverview, type DatasetVersion, errorMessage } from "@/lib/api";
import { versionState, versionTitle } from "@/lib/datasets";
import { dateTime } from "@/lib/format";

const SELECT =
  "h-12 w-full rounded-xl border border-input bg-white px-4 text-base text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring";

export function StateBadge({ v }: { v: DatasetVersion }) {
  const s = versionState(v);
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-3 py-1 text-sm font-bold whitespace-nowrap",
        s.tone === "live" && "bg-ink text-white",
        s.tone === "ok" && "bg-success-bg text-success",
        s.tone === "attention" && "bg-amber-bg text-amber-text",
        s.tone === "muted" && "bg-warm-white text-ink/80",
      )}
    >
      {s.label}
    </span>
  );
}

/** The Datasets page: the live version, the job running now, upload a category file, drafts and history. */
export function DatasetsView() {
  const [state, setState] = useState<{ kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: DatasetsOverview }>({
    kind: "loading",
  });
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((a) => a + 1), []);

  useEffect(() => {
    const ctrl = new AbortController();
    adminApi
      .datasets(ctrl.signal)
      .then((data) => setState({ kind: "ready", data }))
      .catch((e) => !ctrl.signal.aborted && setState({ kind: "error", message: errorMessage(e) }));
    return () => ctrl.abort();
  }, [attempt]);

  const data = state.kind === "ready" ? state.data : null;
  const [finished, setFinished] = useState<DatasetJob | null>(null); // stays shown after the reload
  const [job, setJob] = useJob(data?.active_job ?? null, (j) => {
    setFinished(j);
    reload();
  });
  const shown = job ?? finished;

  if (state.kind === "loading") return <p role="status">Loading datasets…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const d = state.data;
  const drafts = d.versions.filter((v) => v.status === "draft" || v.status === "validated");
  const history = d.versions.filter((v) => v.status === "published" || v.status === "archived");

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-1 rounded-3xl border border-border bg-white p-4 sm:p-5" aria-labelledby="live-heading">
        <h2 id="live-heading" className="text-lg font-bold text-ink">
          Live version
        </h2>
        {d.live ? (
          <p className="text-ink">
            <Link href={`/datasets/${d.live.id}`} className="font-bold text-orange-text underline underline-offset-4">
              {versionTitle(d.live)}
            </Link>{" "}
            {d.live.status === "published" ? (
              <>
                · published {dateTime(d.live.published_at)} by {d.live.published_by}
              </>
            ) : (
              <>· imported, not published through this page yet (publish it to start the history)</>
            )}
          </p>
        ) : (
          <p className="text-ink/80">Nothing imported yet. Run the importer once (README, Phase 2).</p>
        )}
      </section>

      {d.jobs_enabled === false && (
        <section
          role="note"
          aria-labelledby="jobs-off-heading"
          className="flex flex-col gap-1 rounded-3xl border border-border bg-warm-white p-4 sm:p-5"
          data-testid="jobs-off"
        >
          <h2 id="jobs-off-heading" className="text-lg font-bold text-ink">
            Dataset changes are switched off on this server
          </h2>
          <p className="text-ink">
            This is the free demo, which has no background worker. Upload, rebuild, eval and publish are off; the live
            version above is served as it is. Change datasets on the full deployment (docs/deploy-free-demo.md).
          </p>
        </section>
      )}

      {shown && <JobProgress job={shown} canCancel={d.can_manage} onCancelled={reload} />}

      {d.can_manage && d.jobs_enabled !== false && (
        <UploadCard
          overview={d}
          busy={!!job && (job.status === "queued" || job.status === "running")}
          onStarted={(j) => {
            setFinished(null);
            setJob(j);
            reload();
          }}
        />
      )}

      <section aria-labelledby="drafts-heading" className="flex flex-col gap-3">
        <h2 id="drafts-heading" className="text-2xl font-black text-ink">
          Drafts
        </h2>
        <VersionTable rows={drafts} caption="Drafts, newest first" empty="No drafts. Upload a category file to start one." />
      </section>

      <section aria-labelledby="history-heading" className="flex flex-col gap-3">
        <h2 id="history-heading" className="text-2xl font-black text-ink">
          History
        </h2>
        <p className="text-ink/80">Open an archived version to roll a category back to it.</p>
        <VersionTable rows={history} caption="Published and archived versions, newest first" empty="Nothing published yet." history />
      </section>
    </div>
  );
}

function VersionTable({ rows, caption, empty, history }: { rows: DatasetVersion[]; caption: string; empty: string; history?: boolean }) {
  const columns = useMemo<ColumnDef<DatasetVersion, unknown>[]>(
    () => [
      {
        id: "version",
        accessorFn: (v) => versionTitle(v),
        header: "Version",
        cell: ({ row }) => (
          <Link href={`/datasets/${row.original.id}`} className="font-bold text-orange-text underline underline-offset-4">
            {versionTitle(row.original)}
          </Link>
        ),
      },
      { id: "state", accessorFn: (v) => versionState(v).label, header: "Status", cell: ({ row }) => <StateBadge v={row.original} /> },
      { id: "file", accessorFn: (v) => v.upload_name ?? "", header: "File" },
      history
        ? { id: "when", accessorFn: (v) => v.published_at ?? "", header: "Published", cell: ({ row }) => dateTime(row.original.published_at) }
        : {
            id: "eval",
            accessorFn: (v) => v.gate ?? "not run",
            header: "Eval",
            cell: ({ row }) => (row.original.gate === "blocked" ? "Blocked" : row.original.gate === "passed" ? "Passed" : "Not run"),
          },
      { id: "by", accessorFn: (v) => (history ? v.published_by : v.created_by) ?? "", header: history ? "By" : "Uploaded by" },
      ...(history
        ? [{ id: "override", accessorFn: (v: DatasetVersion) => (v.override_reason ? "yes" : ""), header: "Gate overridden" }]
        : [{ id: "created", accessorFn: (v: DatasetVersion) => v.created_at, header: "Uploaded", cell: ({ row }: { row: { original: DatasetVersion } }) => dateTime(row.original.created_at) }]),
    ],
    [history],
  );
  return (
    <DataTable
      data={rows}
      columns={columns}
      caption={caption}
      searchLabel={`Search ${history ? "history" : "drafts"}`}
      pageSize={10}
      empty={empty}
      getRowId={(v) => String(v.id)}
      csv={{
        filename: history ? "dataset-history" : "dataset-drafts",
        columns: [
          { header: "Version", value: (v) => String(v.id) },
          { header: "Categories", value: (v) => v.categories.join(" ") },
          { header: "Status", value: (v) => v.status },
          { header: "File", value: (v) => v.upload_name ?? "" },
          { header: "Created by", value: (v) => v.created_by ?? "" },
          { header: "Published at (UTC)", value: (v) => v.published_at ?? "" },
          { header: "Published by", value: (v) => v.published_by ?? "" },
          { header: "Override reason", value: (v) => v.override_reason ?? "" },
        ],
      }}
    />
  );
}

function UploadCard({
  overview,
  busy,
  onStarted,
}: {
  overview: DatasetsOverview;
  busy: boolean;
  onStarted: (job: DatasetJob) => void;
}) {
  const [code, setCode] = useState("");
  const [fileNo, setFileNo] = useState<number | undefined>();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const category = overview.categories.find((c) => c.code === code);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    if (!category) return setError("Choose the category this file is for.");
    if (!file) return setError("Choose the Excel file (.xlsx).");
    if (category.files.length > 1 && fileNo === undefined) return setError("Choose which of the category's files this replaces.");
    setSending(true);
    adminApi
      .uploadDataset(category.code, file, category.files.length > 1 ? fileNo : undefined)
      .then((r) => {
        setFile(null);
        (e.target as HTMLFormElement).reset();
        onStarted(r.job);
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setSending(false));
  }

  return (
    <section aria-labelledby="upload-heading" className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-4 sm:p-5">
      <h2 id="upload-heading" className="text-2xl font-black text-ink">
        Upload a category file
      </h2>
      <p className="text-ink/80">
        The file becomes a draft: the other categories are copied from the live version, then it is validated and compared with it.
        Nothing changes for customers until you publish.
      </p>
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-2" aria-label="Upload a category file">
        <label className="flex flex-col gap-1 font-semibold text-ink">
          Category
          <select
            name="category"
            className={SELECT}
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
              setFileNo(undefined);
            }}
          >
            <option value="">Choose a category</option>
            {overview.categories.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        {category && category.files.length > 1 && (
          <label className="flex flex-col gap-1 font-semibold text-ink">
            Which file it replaces
            <select name="file_no" className={SELECT} value={fileNo ?? ""} onChange={(e) => setFileNo(e.target.value ? Number(e.target.value) : undefined)}>
              <option value="">Choose a file</option>
              {category.files.map((f) => (
                <option key={f.file_no} value={f.file_no}>
                  File {f.file_no}: {f.live_name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1 font-semibold text-ink">
          Excel file (.xlsx)
          <input
            type="file"
            name="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="min-h-12 rounded-xl border border-input bg-white px-4 py-2.5 text-base text-ink file:mr-3 file:rounded-full file:border-0 file:bg-warm-white file:px-4 file:py-1 file:font-bold focus-visible:ring-3 focus-visible:ring-ring focus-visible:outline-none"
          />
        </label>
        {category && (
          <div className="rounded-2xl bg-warm-white p-3 text-sm text-ink md:col-span-2" data-testid="upload-note">
            Replaces {category.files.map((f) => `file ${f.file_no} (now ${f.live_name})`).join(" or ")}.
            {category.shared_with.length > 0 && (
              <> The same file also holds {category.shared_with.join(", ")}: their rows are replaced too and shown in the diff.</>
            )}
          </div>
        )}
        {error && (
          <p role="alert" className="font-semibold text-orange-text md:col-span-2">
            {error}
          </p>
        )}
        <div className="md:col-span-2">
          <Button type="submit" size="cta" disabled={sending || busy}>
            <Upload aria-hidden="true" className="size-5" />
            {sending ? "Uploading…" : busy ? "Wait for the running job" : "Upload and build draft"}
          </Button>
        </div>
      </form>
    </section>
  );
}
