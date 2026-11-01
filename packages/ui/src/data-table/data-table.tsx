"use client";

import { useId, useMemo, useState, type ReactNode } from "react";
import {
  type ColumnDef,
  type ColumnFiltersState,
  type FilterFn,
  flexRender,
  getCoreRowModel,
  getFacetedUniqueValues,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type Row,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download, Search } from "lucide-react";

import { Button } from "../button";
import { cn } from "../cn";
import { type CsvColumn, downloadCsv, toCsv } from "./csv";

/** A select filter on one column. Without `options`, the values found in the data are offered. Array values (e.g.
 * roles) match when they contain the chosen value. */
export interface DataTableFilter {
  column: string;
  label: string;
  options?: { value: string; label: string }[];
}

export interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  /** Accessible name of the table (also the visually hidden caption). */
  caption: string;
  searchLabel?: string;
  filters?: DataTableFilter[];
  pageSize?: number;
  /** CSV export of every row that matches the search and filters (all pages). */
  csv?: { filename: string; columns: CsvColumn<T>[] };
  /** Shown when nothing matches. */
  empty?: ReactNode;
  /** Extra controls at the right of the toolbar (e.g. an "Invite" button). */
  actions?: ReactNode;
  /** An action on every row the search and filters match (all pages), e.g. "Sign off all 120": gets those rows and
   * the search and filters that selected them. */
  bulk?: (ctx: { rows: T[]; search: string; filters: Record<string, string> }) => ReactNode;
  getRowId?: (row: T) => string;
}

/** Equals for plain values; "contains" for arrays. */
const matches: FilterFn<unknown> = (row, columnId, wanted: string) => {
  const value = row.getValue(columnId);
  return Array.isArray(value) ? value.map(String).includes(wanted) : String(value) === wanted;
};

function searchable(value: unknown): string {
  if (value === null || value === undefined) return "";
  return Array.isArray(value) ? value.join(" ") : String(value);
}

/** Search over every column's value (case-insensitive, all words must appear in the row). */
function rowMatches<T>(row: Row<T>, _columnId: string, query: string): boolean {
  const text = row
    .getAllCells()
    .map((c) => searchable(c.getValue()))
    .join(" ")
    .toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => text.includes(word));
}

/** The admin data table: search, select filters, sorting, pagination and CSV export (TanStack Table). Columns are
 * plain TanStack column definitions; give each an `id` or `accessorKey`. */
export function DataTable<T>({
  data,
  columns,
  caption,
  searchLabel = "Search",
  filters = [],
  pageSize = 20,
  csv,
  empty = "Nothing matches.",
  actions,
  bulk,
  getRowId,
}: DataTableProps<T>) {
  const id = useId();
  const [search, setSearch] = useState("");
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize });

  const filtered = useMemo(() => new Set(filters.map((f) => f.column)), [filters]);
  const cols = useMemo(
    () => columns.map((c) => (c.id && filtered.has(c.id)) || ("accessorKey" in c && filtered.has(String(c.accessorKey))) ? { ...c, filterFn: matches as FilterFn<T> } : c),
    [columns, filtered],
  );

  const table = useReactTable({
    data,
    columns: cols,
    state: { globalFilter: search, columnFilters, sorting, pagination },
    onGlobalFilterChange: setSearch,
    onColumnFiltersChange: (u) => {
      setColumnFilters(u);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    globalFilterFn: rowMatches,
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getFacetedUniqueValues: getFacetedUniqueValues(),
  });

  const rows = table.getRowModel().rows;
  const total = table.getFilteredRowModel().rows.length;
  const first = total === 0 ? 0 : pagination.pageIndex * pagination.pageSize + 1;
  const last = Math.min(total, (pagination.pageIndex + 1) * pagination.pageSize);

  function optionsFor(f: DataTableFilter) {
    if (f.options) return f.options;
    const values = new Set<string>();
    for (const row of table.getCoreRowModel().rows) {
      const v = row.getValue(f.column);
      for (const x of Array.isArray(v) ? v : [v]) if (x !== null && x !== undefined && x !== "") values.add(String(x));
    }
    return [...values].sort().map((v) => ({ value: v, label: v }));
  }

  return (
    <div className="flex flex-col gap-3" data-testid="data-table">
      <div className="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-end">
        <label className="flex flex-col gap-1 text-sm font-semibold text-ink md:min-w-64 md:flex-1">
          {searchLabel}
          <span className="relative">
            <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink/60" />
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className="h-11 w-full rounded-full border border-input bg-white pr-4 pl-9 text-base font-normal outline-none focus-visible:ring-3 focus-visible:ring-ring"
            />
          </span>
        </label>
        {filters.map((f) => (
          <label key={f.column} className="flex flex-col gap-1 text-sm font-semibold text-ink">
            {f.label}
            <select
              value={(table.getColumn(f.column)?.getFilterValue() as string) ?? ""}
              onChange={(e) => table.getColumn(f.column)?.setFilterValue(e.target.value || undefined)}
              className="h-11 rounded-full border border-input bg-white px-4 text-base font-normal outline-none focus-visible:ring-3 focus-visible:ring-ring"
            >
              <option value="">All</option>
              {optionsFor(f).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        ))}
        <div className="flex flex-wrap gap-2 md:ml-auto">
          {csv && (
            <Button
              type="button"
              variant="outline"
              className="h-11 rounded-full px-4 text-base font-semibold"
              onClick={() =>
                // Every row that matches the search and filters, in the shown order, across all pages.
                downloadCsv(csv.filename, toCsv(table.getPrePaginationRowModel().rows.map((r) => r.original), csv.columns))
              }
            >
              <Download aria-hidden="true" className="size-4" />
              Export CSV
            </Button>
          )}
          {actions}
          {bulk?.({
            rows: table.getFilteredRowModel().rows.map((r) => r.original),
            search,
            filters: Object.fromEntries(columnFilters.map((f) => [f.id, String(f.value)])),
          })}
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-border bg-white">
        <table className="w-full border-collapse text-left text-sm" aria-describedby={`${id}-count`}>
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-warm-white">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const sorted = h.column.getIsSorted();
                  const label = flexRender(h.column.columnDef.header, h.getContext());
                  return (
                    <th
                      key={h.id}
                      scope="col"
                      aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                      className="px-3 py-2 font-bold whitespace-nowrap text-ink"
                    >
                      {h.isPlaceholder ? null : h.column.getCanSort() ? (
                        <button
                          type="button"
                          onClick={h.column.getToggleSortingHandler()}
                          className="inline-flex min-h-11 items-center gap-1 rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring"
                        >
                          {label}
                          {sorted === "asc" && <ArrowUp aria-hidden="true" className="size-4" />}
                          {sorted === "desc" && <ArrowDown aria-hidden="true" className="size-4" />}
                        </button>
                      ) : (
                        label
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={table.getVisibleLeafColumns().length} className="px-3 py-6 text-center text-ink/70">
                  {empty}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id} className="border-t border-border align-top">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2 text-ink">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-col items-start gap-2 text-sm text-ink/80 sm:flex-row sm:items-center sm:justify-between">
        <p id={`${id}-count`} aria-live="polite" data-testid="data-table-count">
          {total === 0 ? "No rows" : `Showing ${first}–${last} of ${total}`}
          {total !== data.length && ` (filtered from ${data.length})`}
        </p>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-11 rounded-full px-4"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            <ChevronLeft aria-hidden="true" className="size-4" />
            Previous
          </Button>
          <span className="tabular-nums">
            Page {table.getPageCount() === 0 ? 0 : pagination.pageIndex + 1} of {table.getPageCount()}
          </span>
          <Button
            type="button"
            variant="outline"
            className={cn("h-11 rounded-full px-4")}
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
            <ChevronRight aria-hidden="true" className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
