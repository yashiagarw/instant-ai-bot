"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Button } from "@im/ui/button";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { ErrorBox } from "@/components/error-box";
import { adminApi, type AuditEntry, type AuditQuery, errorMessage } from "@/lib/api";
import { dateTime } from "@/lib/format";

/** Actions the audit log records (docs/permissions.md). */
export const AUDIT_ACTIONS = [
  "staff.login",
  "staff.login_failed",
  "staff.locked",
  "staff.login_locked",
  "staff.logout",
  "staff.two_factor_setup_started",
  "staff.two_factor_enrolled",
  "staff.create",
  "staff.set_roles",
  "staff.activate",
  "staff.deactivate",
  "staff.unlock",
  "staff.reset_two_factor",
  "staff.change_password",
  "customer.reveal_phone",
  "request.set_status",
  "content.review_question",
];
const ENTITY_TYPES = ["staff_user", "staff_session", "customer", "service_request", "generated_question"];

/** "2026-11-01" (a date input, India time) -> the start or end of that day as an ISO time. */
export function dayBoundary(day: string, end: boolean): string | undefined {
  if (!day) return undefined;
  return new Date(`${day}T${end ? "23:59:59.999" : "00:00:00"}+05:30`).toISOString();
}

function Json({ value }: { value: Record<string, unknown> | null }) {
  if (!value) return <span className="text-ink/60">None</span>;
  return <pre className="max-w-md overflow-x-auto rounded-lg bg-warm-white p-2 text-xs whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre>;
}

export function AuditView() {
  const [filters, setFilters] = useState<AuditQuery>({ limit: 500 });
  const [state, setState] = useState<{ kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; rows: AuditEntry[] }>({
    kind: "loading",
  });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    adminApi
      .audit(filters, ctrl.signal)
      .then((rows) => setState({ kind: "ready", rows }))
      .catch((e) => !ctrl.signal.aborted && setState({ kind: "error", message: errorMessage(e) }));
    return () => ctrl.abort();
  }, [filters, attempt]);

  function apply(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setState({ kind: "loading" });
    setFilters({
      action: String(f.get("action") || "") || undefined,
      entity_type: String(f.get("entity_type") || "") || undefined,
      actor: String(f.get("actor") || "").trim() || undefined,
      since: dayBoundary(String(f.get("since") || ""), false),
      until: dayBoundary(String(f.get("until") || ""), true),
      limit: 500,
    });
  }

  const columns = useMemo<ColumnDef<AuditEntry, unknown>[]>(
    () => [
      { accessorKey: "at", header: "Time (IST)", cell: ({ row }) => <span className="whitespace-nowrap">{dateTime(row.original.at)}</span> },
      { accessorKey: "actor_label", header: "Who" },
      { accessorKey: "action", header: "Action", cell: ({ row }) => <code className="text-xs font-bold">{row.original.action}</code> },
      {
        id: "entity",
        accessorFn: (r) => `${r.entity_type} ${r.entity_id ?? ""}`,
        header: "On",
        cell: ({ row }) => (
          <span className="flex flex-col">
            <span>{row.original.entity_type}</span>
            {row.original.entity_id && <span className="font-mono text-xs text-ink/70">{row.original.entity_id}</span>}
          </span>
        ),
      },
      {
        id: "change",
        header: "Before / after",
        enableSorting: false,
        accessorFn: (r) => JSON.stringify([r.before, r.after]),
        cell: ({ row }) =>
          row.original.before || row.original.after ? (
            <details>
              <summary className="min-h-11 cursor-pointer py-2 font-semibold text-orange-text">Show</summary>
              <div className="flex flex-col gap-2 py-1">
                <span className="text-xs font-bold">Before</span>
                <Json value={row.original.before} />
                <span className="text-xs font-bold">After</span>
                <Json value={row.original.after} />
              </div>
            </details>
          ) : (
            <span className="text-ink/60">None</span>
          ),
      },
      { accessorKey: "ip", header: "IP", cell: ({ row }) => <span className="font-mono text-xs">{row.original.ip ?? ""}</span> },
    ],
    [],
  );

  const select = "h-11 rounded-full border border-input bg-white px-4 text-base outline-none focus-visible:ring-3 focus-visible:ring-ring";
  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={apply} className="grid gap-3 rounded-3xl border border-border bg-white p-4 sm:grid-cols-2 lg:grid-cols-6" aria-label="Audit log filters">
        <label className="flex flex-col gap-1 text-sm font-semibold text-ink lg:col-span-2">
          Action
          <select name="action" className={select} defaultValue="">
            <option value="">Any action</option>
            {AUDIT_ACTIONS.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold text-ink">
          On
          <select name="entity_type" className={select} defaultValue="">
            <option value="">Anything</option>
            {ENTITY_TYPES.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold text-ink">
          Who (email)
          <input name="actor" className={select} placeholder="part of an email, or cli" />
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold text-ink">
          From
          <input name="since" type="date" className={select} />
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold text-ink">
          To
          <input name="until" type="date" className={select} />
        </label>
        <Button type="submit" className="h-11 rounded-full px-5 text-base font-bold sm:col-span-2 lg:col-span-6 lg:justify-self-start">
          Apply filters
        </Button>
      </form>

      {state.kind === "loading" && <p role="status">Loading the audit log…</p>}
      {state.kind === "error" && <ErrorBox message={state.message} onRetry={() => setAttempt((a) => a + 1)} />}
      {state.kind === "ready" && (
        <DataTable
          data={state.rows}
          columns={columns}
          caption="Audit log, newest first"
          searchLabel="Search these entries"
          pageSize={25}
          csv={{
            filename: "audit-log",
            columns: [
              { header: "Time (UTC)", value: (r) => r.at },
              { header: "Who", value: (r) => r.actor_label },
              { header: "Action", value: (r) => r.action },
              { header: "Entity type", value: (r) => r.entity_type },
              { header: "Entity id", value: (r) => r.entity_id ?? "" },
              { header: "Before", value: (r) => (r.before ? JSON.stringify(r.before) : "") },
              { header: "After", value: (r) => (r.after ? JSON.stringify(r.after) : "") },
              { header: "IP", value: (r) => r.ip ?? "" },
            ],
          }}
          getRowId={(r) => String(r.id)}
          empty="No entries match these filters."
        />
      )}
    </div>
  );
}
