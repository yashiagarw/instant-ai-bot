"use client";

import Link from "next/link";
import { useCallback } from "react";

import { Button } from "@im/ui/button";
import { ErrorBox } from "@/components/error-box";
import { SaveStatus, useStatus } from "@/components/form";
import { EditorSummaryView, short } from "@/components/knowledge/editor-summary";
import { useDraft, useDraftData } from "@/components/knowledge/draft";
import { adminApi, errorMessage } from "@/lib/api";
import { dateTime } from "@/lib/format";

/** What this draft changes, newest first, each with a revert. The same summary appears on the publish page. */
export function ChangesTab() {
  const { draft, writable, touched } = useDraft();
  const { state, reload } = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.edits(v, s), []));
  const [status, setStatus] = useStatus();
  if (state.kind === "loading") return <p role="status">Loading changes…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const { edits, summary, conflicts, orphans } = state.data;
  return (
    <div className="flex flex-col gap-4">
      <EditorSummaryView summary={{ ...summary, conflicts, orphans }} />
      <p className="text-ink/80">
        Publish this draft on the{" "}
        <Link href={`/datasets/${draft?.id}`} className="font-bold text-orange-text underline underline-offset-4">
          Datasets page
        </Link>{" "}
        (evaluation first). Edits are kept as overrides: a later Excel import does not undo them.
      </p>
      <SaveStatus status={status} />
      {edits.length === 0 && <p className="text-ink/70">No edits in this draft yet.</p>}
      <ol className="flex flex-col gap-3" aria-label="Edits in this draft">
        {edits.map((e) => (
          <li key={e.id} className="flex flex-col gap-2 rounded-2xl border border-border bg-white p-3">
            <p className="flex flex-wrap items-center gap-2 font-bold text-ink">
              {e.name}
              <span className="rounded-full bg-warm-white px-2 text-xs">{e.op}</span>
              {e.safety && <span className="rounded-full border border-danger px-2 text-xs text-danger">safety</span>}
            </p>
            <p className="text-sm text-ink/75">
              {e.table} · {e.by} · {dateTime(e.at)}
              {e.reason && <> · {e.reason}</>}
            </p>
            {e.changes.length > 0 && e.op !== "deleted" && (
              <dl className="grid gap-1 text-sm sm:grid-cols-[max-content_1fr]">
                {e.changes.map((c) => (
                  <div key={c.field} className="contents">
                    <dt className="font-semibold">{c.field}</dt>
                    <dd>
                      <span className="text-ink/70">{short(c.before)}</span> → {short(c.after)}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            {writable && e.status === "draft" && (
              <Button
                type="button"
                variant="outline"
                className="h-11 self-start rounded-full px-4 text-base"
                onClick={() =>
                  adminApi
                    .revertEdit(draft!.id, e.id)
                    .then(() => {
                      setStatus({ kind: "saved", text: `Reverted: ${e.name}` });
                      touched();
                      reload();
                    })
                    .catch((err) => setStatus({ kind: "error", text: errorMessage(err) }))
                }
              >
                Revert
              </Button>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
