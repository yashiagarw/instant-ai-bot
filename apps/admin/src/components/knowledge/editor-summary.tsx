"use client";

import type { EditorSummary } from "@/lib/api";

export function short(value: unknown): string {
  if (value === null || value === undefined || value === "") return "(empty)";
  const s = typeof value === "string" ? value : JSON.stringify(value);
  return s.length > 160 ? `${s.slice(0, 159)}…` : s;
}

/** Editor changes of a draft: counts per table, every safety change by name with old and new values, conflicts with
 * the imported data and edits that could not be applied. Shown on the Changes tab and the publish page. */
export function EditorSummaryView({ summary }: { summary: EditorSummary }) {
  const tables = Object.entries(summary.tables);
  const conflicts = summary.conflicts ?? [];
  const orphans = summary.orphans ?? [];
  if (!tables.length && !conflicts.length && !orphans.length) return <p className="text-ink/70">No editor changes in this version.</p>;
  return (
    <div className="flex flex-col gap-3" data-testid="editor-summary">
      {tables.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-md text-left">
            <caption className="sr-only">Editor changes per table</caption>
            <thead>
              <tr className="border-b-2 border-ink">
                <th scope="col" className="p-2">Table</th>
                <th scope="col" className="p-2">Added</th>
                <th scope="col" className="p-2">Changed</th>
                <th scope="col" className="p-2">Deleted</th>
                <th scope="col" className="p-2">Signed off</th>
              </tr>
            </thead>
            <tbody>
              {tables.map(([table, c]) => (
                <tr key={table} className="border-b border-border">
                  <th scope="row" className="p-2 text-left font-semibold">
                    {table}
                  </th>
                  <td className="p-2">{c.added ?? 0}</td>
                  <td className="p-2">{c.changed ?? 0}</td>
                  <td className="p-2">{c.deleted ?? 0}</td>
                  <td className="p-2">{c["signed off"] ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {summary.safety.length > 0 && (
        <div className="flex flex-col gap-2 rounded-2xl border-2 border-danger p-3" data-testid="safety-changes">
          <h3 className="font-bold text-danger">Safety rule changes ({summary.safety.length})</h3>
          <ul className="flex flex-col gap-2">
            {summary.safety.map((s) => (
              <li key={s.edit} className="text-ink">
                <strong>{s.name}</strong> <span className="text-sm text-ink/70">by {s.by}</span>
                <ul className="pl-4 text-sm">
                  {s.changes.map((c) => (
                    <li key={c.field}>
                      {c.field}: <span className="text-ink/70">{short(c.before)}</span> → {short(c.after)}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}
      {conflicts.length > 0 && (
        <div className="rounded-2xl bg-amber-bg p-3 text-amber-text">
          <h3 className="font-bold">The imported file also changed these edited items (the edit is kept)</h3>
          <ul className="list-disc pl-5">
            {conflicts.map((c) => (
              <li key={c.edit}>
                {c.name}: {c.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {orphans.length > 0 && (
        <div className="rounded-2xl bg-amber-bg p-3 text-amber-text">
          <h3 className="font-bold">Edits not applied (the item is not in this version)</h3>
          <ul className="list-disc pl-5">
            {orphans.map((c) => (
              <li key={c.edit}>
                {c.name}: {c.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
