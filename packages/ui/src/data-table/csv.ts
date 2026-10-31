/** CSV for spreadsheets: RFC 4180 quoting, a BOM so Excel reads UTF-8, and cells that start like a formula
 * (= + - @, tab, carriage return) prefixed with ' so a spreadsheet never runs them. */

export interface CsvColumn<T> {
  header: string;
  value: (row: T) => unknown;
}

const FORMULA = /^[=+\-@\t\r]/;

export function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  let text = Array.isArray(value) ? value.join("; ") : value instanceof Date ? value.toISOString() : String(value);
  if (FORMULA.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv<T>(rows: T[], columns: CsvColumn<T>[]): string {
  const lines = [columns.map((c) => csvCell(c.header)).join(",")];
  for (const row of rows) lines.push(columns.map((c) => csvCell(c.value(row))).join(","));
  return "﻿" + lines.join("\r\n") + "\r\n";
}

export function downloadCsv(filename: string, csv: string): void {
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
