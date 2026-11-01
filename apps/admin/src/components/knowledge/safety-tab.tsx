"use client";

import { useCallback, useMemo, useState } from "react";

import { Button } from "@im/ui/button";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { ErrorBox } from "@/components/error-box";
import { EditedBadge } from "@/components/form";
import { useDraft, useDraftData } from "@/components/knowledge/draft";
import { SAFETY_STATUS, SafetyRuleDialog } from "@/components/knowledge/safety-form";
import { adminApi, type SafetyRuleRow } from "@/lib/api";

/** Every safety rule of the draft: emergency (global) rules and fault rules, with their trigger phrases. */
export function SafetyTab() {
  const { writable } = useDraft();
  const { state, reload } = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.safetyRules(v, s), []));
  const [editing, setEditing] = useState<SafetyRuleRow | null>(null);
  const columns = useMemo<ColumnDef<SafetyRuleRow, unknown>[]>(
    () => [
      {
        id: "rule",
        accessorFn: (r) => (r.scope === "global" ? `emergency ${r.key}` : r.key),
        header: "Rule",
        cell: ({ row }) => (
          <span className="flex flex-col">
            <span className="font-bold">{row.original.scope === "global" ? "Emergency rule" : row.original.fault_key}</span>
            <span className="text-xs text-ink/70">{row.original.scope === "global" ? row.original.key.replace("global/", "") : row.original.source}</span>
          </span>
        ),
      },
      { accessorKey: "risk_level", header: "Risk" },
      { id: "status", accessorFn: (r) => r.status, header: "Status", cell: ({ row }) => SAFETY_STATUS[row.original.status] },
      { id: "category", accessorFn: (r) => r.category ?? "emergency", header: "Category" },
      {
        id: "what",
        accessorFn: (r) => `${r.stop_driving_trigger} ${r.roadside_action} ${r.trigger_phrases.join(" ")}`,
        header: "What it says",
        enableSorting: false,
        cell: ({ row }) => (
          <span className="flex flex-col gap-1 text-sm">
            {row.original.stop_driving_trigger || row.original.roadside_action}
            {row.original.trigger_phrases.length > 0 && <span className="text-ink/70">Triggers: {row.original.trigger_phrases.join(", ")}</span>}
            <EditedBadge show={row.original.edit} />
          </span>
        ),
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) =>
          writable ? (
            <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => setEditing(row.original)}>
              Edit
            </Button>
          ) : null,
      },
    ],
    [writable],
  );
  if (state.kind === "loading") return <p role="status">Loading safety rules…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  return (
    <>
      <p className="text-ink/80">Changing a safety rule always shows a warning and is audited with its old and new values.</p>
      <DataTable
        data={state.data}
        columns={columns}
        caption="Safety rules"
        searchLabel="Search safety rules"
        filters={[
          { column: "status", label: "Status", options: Object.entries(SAFETY_STATUS).map(([value, label]) => ({ value, label })) },
          { column: "risk_level", label: "Risk", options: ["high", "medium", "low"].map((x) => ({ value: x, label: x })) },
        ]}
        pageSize={20}
        getRowId={(r) => r.key}
      />
      {editing && <SafetyRuleDialog rule={editing} open onOpenChange={(o) => !o && setEditing(null)} onSaved={reload} />}
    </>
  );
}
