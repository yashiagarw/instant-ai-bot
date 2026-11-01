"use client";

import { useCallback, useMemo, useState } from "react";

import { Button } from "@im/ui/button";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { ErrorBox } from "@/components/error-box";
import { SaveStatus, useStatus } from "@/components/form";
import { useDraft, useDraftData } from "@/components/knowledge/draft";
import { adminApi, errorMessage, type SignoffItem } from "@/lib/api";

const ENTITY: Record<SignoffItem["entity"], string> = {
  question: "Question",
  phrase: "Customer phrase",
  safety_rule: "Safety rule",
  image_label: "Photo label",
};

/** Items checked automatically ("claude_code (auto, pending mechanic sign-off)") waiting for a person. Signing off
 * records your name and today's date in the draft; published with it. */
export function SignoffTab() {
  const { draft, writable, touched } = useDraft();
  const { state, reload } = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.signoffQueue(v, s), []));
  const [pendingOnly, setPendingOnly] = useState(true);
  const [status, setStatus] = useStatus();

  const signOff = useCallback(
    (item: SignoffItem) =>
      adminApi
        .signOff(draft!.id, item.entity, item.key)
        .then(() => {
          setStatus({ kind: "saved", text: `Signed off: ${item.text.slice(0, 80)}` });
          touched();
          reload();
        })
        .catch((e) => setStatus({ kind: "error", text: errorMessage(e) })),
    [draft, reload, setStatus, touched],
  );

  const columns = useMemo<ColumnDef<SignoffItem, unknown>[]>(
    () => [
      { id: "entity", accessorFn: (i) => i.entity, header: "Type", cell: ({ row }) => ENTITY[row.original.entity] },
      { accessorKey: "text", header: "Item", cell: ({ row }) => <span lang="mul">{row.original.text}</span> },
      { id: "category", accessorFn: (i) => i.category ?? "", header: "Category" },
      { id: "reviewed_by", accessorFn: (i) => i.reviewed_by ?? "", header: "Reviewed by" },
      {
        id: "state",
        accessorFn: (i) => (i.edit ? "signed off in this draft" : i.pending ? "pending" : "reviewed"),
        header: "Status",
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) =>
          writable && row.original.pending ? (
            <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => void signOff(row.original)}>
              Sign off as me
            </Button>
          ) : null,
      },
    ],
    [writable, signOff],
  );

  if (state.kind === "loading") return <p role="status">Loading items waiting for sign-off…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const rows = pendingOnly ? state.data.filter((i) => i.pending) : state.data;
  return (
    <>
      <label className="flex min-h-11 items-center gap-3 font-semibold text-ink">
        <input type="checkbox" className="size-5 accent-cta" checked={pendingOnly} onChange={(e) => setPendingOnly(e.target.checked)} />
        Show only items still pending sign-off ({state.data.filter((i) => i.pending).length})
      </label>
      <SaveStatus status={status} />
      <DataTable
        data={rows}
        columns={columns}
        caption="Items for sign-off"
        searchLabel="Search items"
        filters={[{ column: "entity", label: "Type", options: Object.entries(ENTITY).map(([value, label]) => ({ value, label })) }]}
        pageSize={25}
        getRowId={(i) => `${i.entity}:${i.key}`}
        empty="Nothing waiting for sign-off."
        csv={{
          filename: `signoff-v${draft?.id}`,
          columns: [
            { header: "Type", value: (i) => ENTITY[i.entity] },
            { header: "Key", value: (i) => i.key },
            { header: "Item", value: (i) => i.text },
            { header: "Reviewed by", value: (i) => i.reviewed_by ?? "" },
            { header: "Pending", value: (i) => (i.pending ? "yes" : "") },
          ],
        }}
      />
    </>
  );
}
