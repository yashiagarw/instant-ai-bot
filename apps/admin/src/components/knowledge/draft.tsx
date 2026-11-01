"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { PenLine } from "lucide-react";

import { Button } from "@im/ui/button";
import { JobProgress, useJob } from "@/components/datasets/job-progress";
import { ErrorBox } from "@/components/error-box";
import { useMe } from "@/components/staff-shell";
import { adminApi, type DatasetJob, type Draft, errorMessage } from "@/lib/api";

interface DraftState {
  draft: Draft | null;
  drafts: Draft[];
  canEdit: boolean;
  /** Edits are allowed: an open, built draft and the knowledge.edit permission. */
  writable: boolean;
  reload: () => void;
  /** Tell the bar an edit was saved (the draft's edit count changes). */
  touched: () => void;
}

const DraftContext = createContext<DraftState | null>(null);

export function useDraft(): DraftState {
  const ctx = useContext(DraftContext);
  if (!ctx) throw new Error("useDraft outside DraftProvider");
  return ctx;
}

/** Which draft the editors read and write: ?draft=ID, else the newest open draft. */
export function DraftProvider({ children }: { children: ReactNode }) {
  const { me } = useMe();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((a) => a + 1), []);
  const [job, setJob] = useJob(null, reload);

  useEffect(() => {
    const ctrl = new AbortController();
    adminApi
      .drafts(ctrl.signal)
      .then((d) => {
        setDrafts(d);
        setError("");
      })
      .catch((e) => !ctrl.signal.aborted && setError(errorMessage(e)));
    return () => ctrl.abort();
  }, [attempt]);

  // While a draft is being built, look again every few seconds.
  const building = drafts?.some((d) => d.building) ?? false;
  useEffect(() => {
    if (!building) return;
    const t = setInterval(reload, 3000);
    return () => clearInterval(t);
  }, [building, reload]);

  const wanted = Number(params.get("draft")) || null;
  const draft = drafts ? (drafts.find((d) => d.id === wanted) ?? drafts[0] ?? null) : null;
  const canEdit = me.permissions.includes("knowledge.edit");
  const value = useMemo<DraftState>(
    () => ({
      draft,
      drafts: drafts ?? [],
      canEdit,
      writable: canEdit && !!draft && !draft.building,
      reload,
      touched: reload,
    }),
    [draft, drafts, canEdit, reload],
  );

  function choose(id: number) {
    const q = new URLSearchParams(params.toString());
    q.set("draft", String(id));
    router.replace(`${pathname}?${q.toString()}`);
  }

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!drafts) return <p role="status">Loading drafts…</p>;

  return (
    <DraftContext.Provider value={value}>
      <section
        aria-label="Draft being edited"
        className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between"
      >
        {draft ? (
          <div className="flex flex-col gap-1">
            <p className="flex items-center gap-2 font-bold text-ink">
              <PenLine aria-hidden="true" className="size-5 text-orange-text" />
              Editing draft v{draft.id}
              <span className="font-normal text-ink/75">
                ({draft.origin === "edit" ? "edit draft" : `upload: ${draft.category_code}`}, {draft.edits} edits)
              </span>
            </p>
            <p className="text-sm text-ink/75">
              Changes stay in this draft until it is published on the{" "}
              <Link href={`/datasets/${draft.id}`} className="font-bold text-orange-text underline underline-offset-4">
                Datasets page
              </Link>
              . Customers see nothing before that.
              {draft.stale && " Another version was published since: rebuild it there (your edits are kept)."}
              {draft.building && " Building the draft…"}
            </p>
          </div>
        ) : (
          <p className="text-ink">No open draft. {canEdit ? "Start one to edit (a copy of the live version)." : "Nothing to show yet."}</p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          {drafts.length > 1 && (
            <label className="flex items-center gap-2 font-semibold text-ink">
              Draft
              <select
                className="h-11 rounded-full border border-input bg-white px-4"
                value={draft?.id ?? ""}
                onChange={(e) => choose(Number(e.target.value))}
              >
                {drafts.map((d) => (
                  <option key={d.id} value={d.id}>
                    v{d.id} · {d.origin === "edit" ? "edits" : d.category_code} ({d.edits})
                  </option>
                ))}
              </select>
            </label>
          )}
          {canEdit && !drafts.some((d) => d.origin === "edit") && (
            <StartDraft
              onStarted={(j, id) => {
                setJob(j);
                choose(id);
                reload();
              }}
            />
          )}
        </div>
      </section>
      {job && (job.status === "queued" || job.status === "running" || job.status === "failed") && <JobProgress job={job} />}
      {children}
    </DraftContext.Provider>
  );
}

function StartDraft({ onStarted }: { onStarted: (job: DatasetJob, id: number) => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-col gap-1">
      <Button
        type="button"
        className="h-11 rounded-full px-5 text-base font-bold"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError("");
          adminApi
            .startDraft()
            .then((r) => onStarted(r.job, r.version_id))
            .catch((e) => setError(errorMessage(e)))
            .finally(() => setBusy(false));
        }}
      >
        {busy ? "Starting…" : "Start an edit draft"}
      </Button>
      {error && (
        <p role="alert" className="text-sm font-semibold text-orange-text">
          {error}
        </p>
      )}
    </div>
  );
}

/** Loads something from the selected draft; reloads when the draft changes or `reload()` is called. */
export function useDraftData<T>(fetcher: ((v: number, signal: AbortSignal) => Promise<T>) | null) {
  const { draft } = useDraft();
  const [state, setState] = useState<{ kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T }>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const id = draft && !draft.building ? draft.id : null;
  useEffect(() => {
    if (!id || !fetcher) return;
    const ctrl = new AbortController();
    fetcher(id, ctrl.signal)
      .then((data) => setState({ kind: "ready", data }))
      .catch((e) => !ctrl.signal.aborted && setState({ kind: "error", message: errorMessage(e) }));
    return () => ctrl.abort();
  }, [id, fetcher, attempt]);
  const reload = useCallback(() => setAttempt((a) => a + 1), []);
  return { state, reload, version: id };
}
