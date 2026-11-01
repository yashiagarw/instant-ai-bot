import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { type ColumnDef, csvCell, DataTable, toCsv } from "./index";

interface Person {
  id: string;
  name: string;
  email: string;
  roles: string[];
  active: boolean;
}

const PEOPLE: Person[] = Array.from({ length: 25 }, (_, i) => ({
  id: `p${i}`,
  name: i === 3 ? "Asha Verma" : `Person ${String(i).padStart(2, "0")}`,
  email: `p${i}@im.test`,
  roles: i % 5 === 0 ? ["super_admin", "mechanic"] : i % 2 ? ["mechanic"] : ["support_agent"],
  active: i !== 7,
}));

const COLUMNS: ColumnDef<Person, unknown>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "email", header: "Email" },
  { accessorKey: "roles", header: "Roles", cell: (c) => (c.getValue() as string[]).join(", "), enableSorting: false },
  { id: "status", accessorFn: (p) => (p.active ? "Active" : "Disabled"), header: "Status" },
];

let csv: string | null = null;
beforeEach(() => {
  csv = null;
  URL.createObjectURL = vi.fn((blob: Blob) => {
    void blob.text().then((t) => (csv = t));
    return "blob:csv";
  });
  URL.revokeObjectURL = vi.fn();
  HTMLAnchorElement.prototype.click = vi.fn();
});
afterEach(cleanup);

function table() {
  render(
    <DataTable
      data={PEOPLE}
      columns={COLUMNS}
      caption="Staff"
      searchLabel="Search staff"
      filters={[
        { column: "roles", label: "Role" },
        { column: "status", label: "Status", options: [{ value: "Active", label: "Active" }, { value: "Disabled", label: "Disabled" }] },
      ]}
      pageSize={10}
      csv={{ filename: "staff", columns: [{ header: "Name", value: (p) => p.name }, { header: "Roles", value: (p) => p.roles }] }}
      getRowId={(p) => p.id}
    />,
  );
}

const bodyRows = () => within(screen.getByRole("table", { name: "Staff" })).getAllByRole("row").slice(1);
const count = () => screen.getByTestId("data-table-count").textContent;

test("pages through the rows", () => {
  table();
  expect(bodyRows()).toHaveLength(10);
  expect(count()).toBe("Showing 1–10 of 25");
  fireEvent.click(screen.getByRole("button", { name: /Next/ }));
  fireEvent.click(screen.getByRole("button", { name: /Next/ }));
  expect(count()).toBe("Showing 21–25 of 25");
  expect(screen.getByRole("button", { name: /Next/ })).toHaveProperty("disabled", true);
  expect(screen.getByText("Page 3 of 3")).toBeDefined();
});

test("searches every column, all words, case-insensitive; empty result says so", () => {
  table();
  fireEvent.change(screen.getByRole("searchbox", { name: "Search staff" }), { target: { value: "asha VERMA" } });
  expect(bodyRows()).toHaveLength(1);
  expect(count()).toBe("Showing 1–1 of 1 (filtered from 25)");
  fireEvent.change(screen.getByRole("searchbox", { name: "Search staff" }), { target: { value: "support_agent" } });
  expect(count()).toMatch(/of 10 \(filtered/);
  fireEvent.change(screen.getByRole("searchbox", { name: "Search staff" }), { target: { value: "nobody here" } });
  expect(screen.getByText("Nothing matches.")).toBeDefined();
});

test("filters: options come from the data, arrays match when they contain the value", () => {
  table();
  const role = screen.getByRole("combobox", { name: "Role" });
  expect([...role.querySelectorAll("option")].map((o) => o.textContent)).toEqual(["All", "mechanic", "super_admin", "support_agent"]);
  fireEvent.change(role, { target: { value: "super_admin" } });
  expect(count()).toBe("Showing 1–5 of 5 (filtered from 25)");
  fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "Disabled" } });
  expect(screen.getByText("Nothing matches.")).toBeDefined(); // person 7 is not a super admin
  fireEvent.change(role, { target: { value: "" } });
  expect(bodyRows().map((r) => r.textContent)).toEqual(["Person 07p7@im.testmechanicDisabled"]);
});

test("sorts by a column header", () => {
  table();
  const name = screen.getByRole("button", { name: "Name" });
  fireEvent.click(name);
  expect(screen.getByRole("columnheader", { name: /Name/ }).getAttribute("aria-sort")).toBe("ascending");
  expect(bodyRows()[0].textContent).toMatch(/^Asha Verma/);
  fireEvent.click(name);
  expect(bodyRows()[0].textContent).toMatch(/^Person 24/);
});

test("CSV export has every matching row (all pages), safely quoted", async () => {
  table();
  fireEvent.change(screen.getByRole("combobox", { name: "Role" }), { target: { value: "mechanic" } });
  fireEvent.click(screen.getByRole("button", { name: /Export CSV/ }));
  await vi.waitFor(() => expect(csv).not.toBeNull());
  const lines = csv!.replace("﻿", "").trim().split("\r\n");
  expect(lines[0]).toBe("Name,Roles");
  expect(lines).toHaveLength(1 + 15); // 12 odd + 3 more with super_admin + mechanic
  expect(lines).toContain("Person 00,super_admin; mechanic");
});

test("CSV cells: quotes, commas, new lines and formulas", () => {
  expect(csvCell('say "hi", ok')).toBe('"say ""hi"", ok"');
  expect(csvCell("=HYPERLINK(1)")).toBe("'=HYPERLINK(1)");
  expect(csvCell("-1+2")).toBe("'-1+2");
  expect(csvCell(null)).toBe("");
  expect(toCsv([{ a: "x\ny" }], [{ header: "A", value: (r) => r.a }])).toBe('﻿A\r\n"x\ny"\r\n');
});

test("a bulk action gets every row the search matches (all pages) and the search used", () => {
  const seen: { n: number; search: string }[] = [];
  render(
    <DataTable
      data={Array.from({ length: 30 }, (_, i) => ({ name: i % 2 ? `odd ${i}` : `even ${i}` }))}
      columns={[{ accessorKey: "name", header: "Name" }] as ColumnDef<{ name: string }, unknown>[]}
      caption="Rows"
      pageSize={5}
      bulk={({ rows, search }) => {
        seen.push({ n: rows.length, search });
        return <button type="button">Act on {rows.length}</button>;
      }}
    />,
  );
  expect(screen.getByRole("button", { name: "Act on 30" })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Search"), { target: { value: "odd" } });
  expect(screen.getByRole("button", { name: "Act on 15" })).toBeTruthy();
  expect(seen.at(-1)).toEqual({ n: 15, search: "odd" });
});
