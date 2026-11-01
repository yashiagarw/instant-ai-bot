"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Download, Plus } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { EditedBadge, SaveStatus, Select, TextInput, useStatus } from "@/components/form";
import { DraftProvider, useDraft, useDraftData } from "@/components/knowledge/draft";
import { PriceDialog } from "@/components/parts/price-dialog";
import { adminApi, errorMessage, type ImportResult, type LabourRow, type PartRow, type PriceRow, type ZoneRateRow } from "@/lib/api";
import { date } from "@/lib/format";
import { type LabourForm, labourSchema, type PartForm, partSchema, SEGMENTS, type ZoneRateForm, zoneRateSchema } from "@/lib/schemas";

const TABS = [
  { key: "parts", label: "Parts" },
  { key: "prices", label: "Prices" },
  { key: "labour", label: "Labour rates" },
  { key: "import", label: "Import CSV" },
] as const;

const inr = (n: number | null | undefined) => (n === null || n === undefined ? "–" : `₹${n.toLocaleString("en-IN")}`);

export function PartsView() {
  return (
    <DraftProvider>
      <Tabs />
    </DraftProvider>
  );
}

function Tabs() {
  const { draft } = useDraft();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = TABS.find((t) => t.key === params.get("tab"))?.key ?? "parts";
  if (!draft || draft.building) return null;
  return (
    <div className="flex flex-col gap-4">
      <div role="tablist" aria-label="Parts & Prices" className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            type="button"
            id={`tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`panel-${t.key}`}
            onClick={() => {
              const q = new URLSearchParams(params.toString());
              q.set("tab", t.key);
              router.replace(`${pathname}?${q.toString()}`, { scroll: false });
            }}
            className={cn(
              "min-h-11 rounded-full border-2 px-4 font-bold outline-none focus-visible:ring-3 focus-visible:ring-ring",
              tab === t.key ? "border-ink bg-ink text-white" : "border-border bg-white text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="flex flex-col gap-4">
        {tab === "parts" && <PartsTab />}
        {tab === "prices" && <PricesTab />}
        {tab === "labour" && <LabourTab />}
        {tab === "import" && <ImportTab />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- parts

function PartsTab() {
  const { draft, writable } = useDraft();
  const { state, reload } = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.parts(v, s), []));
  const [creating, setCreating] = useState(false);
  const columns = useMemo<ColumnDef<PartRow, unknown>[]>(
    () => [
      {
        accessorKey: "description",
        header: "Part",
        cell: ({ row }) => (
          <span className="flex flex-col">
            <Link href={`/parts/${encodeURIComponent(row.original.key)}?draft=${draft?.id}`} className="font-bold text-orange-text underline underline-offset-4">
              {row.original.description}
            </Link>
            <span className="text-xs text-ink/70">{row.original.key}</span>
          </span>
        ),
      },
      { accessorKey: "part_type", header: "Type" },
      { accessorKey: "brand", header: "Brand" },
      { id: "price", accessorFn: (p) => p.price_min ?? 0, header: "Prices", cell: ({ row }) => (row.original.prices ? `${row.original.prices} · ${inr(row.original.price_min)}–${inr(row.original.price_max)}` : "none") },
      { accessorKey: "fits", header: "Fits" },
      { id: "flags", accessorFn: (p) => (p.second_look ? "second look" : p.edited ? "edited" : ""), header: "Flags", cell: ({ row }) => (
        <span className="flex flex-wrap gap-1">
          {row.original.second_look > 0 && <EditedBadge show label={`${row.original.second_look} need a second look`} />}
          <EditedBadge show={row.original.edited} />
        </span>
      ) },
    ],
    [draft?.id],
  );
  if (state.kind === "loading") return <p role="status">Loading parts…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  return (
    <>
      <DataTable
        data={state.data}
        columns={columns}
        caption="Parts"
        searchLabel="Search parts (name, type, brand, number)"
        filters={[{ column: "flags", label: "Flags", options: [{ value: "second look", label: "Needs a second look" }, { value: "edited", label: "Edited in this draft" }] }]}
        pageSize={25}
        getRowId={(p) => p.key}
        actions={
          writable && (
            <Button type="button" className="h-11 rounded-full px-5 text-base font-bold" onClick={() => setCreating(true)}>
              <Plus aria-hidden="true" className="size-5" /> New part
            </Button>
          )
        }
        csv={{
          filename: `parts-v${draft?.id}`,
          columns: [
            { header: "Key", value: (p) => p.key },
            { header: "Part", value: (p) => p.description },
            { header: "Type", value: (p) => p.part_type },
            { header: "Brand", value: (p) => p.brand },
            { header: "Number", value: (p) => p.part_number },
            { header: "Lowest price", value: (p) => String(p.price_min ?? "") },
            { header: "Highest price", value: (p) => String(p.price_max ?? "") },
          ],
        }}
      />
      {creating && <NewPart onClose={() => setCreating(false)} />}
    </>
  );
}

export function PartFields({ form }: { form: ReturnType<typeof useForm<PartForm>> }) {
  const e = form.formState.errors;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <TextInput label="Description" error={e.description} className="md:col-span-2" {...form.register("description")} />
      <TextInput label="Part type (e.g. Brake pad set)" error={e.part_type} {...form.register("part_type")} />
      <TextInput label="Brand" error={e.brand} {...form.register("brand")} />
      <Select
        label="Brand kind"
        options={[
          { value: "unspecified", label: "not stated" },
          { value: "oem", label: "OEM (carmaker genuine)" },
          { value: "oes", label: "OES (carmaker's supplier)" },
          { value: "aftermarket", label: "aftermarket" },
        ]}
        {...form.register("brand_kind")}
      />
      <TextInput label="Part number" error={e.part_number} {...form.register("part_number")} />
      <TextInput label="Quantity" type="number" error={e.quantity} {...form.register("quantity", { valueAsNumber: true })} />
      <Select label="Kind" options={[{ value: "part", label: "part" }, { value: "consumable", label: "consumable (oil, coolant ...)" }]} {...form.register("kind")} />
      <Select
        label="Segment (generic parts only)"
        error={e.segment}
        options={[{ value: "", label: "not set" }, ...SEGMENTS.map((x) => ({ value: x, label: x }))]}
        {...form.register("segment", { setValueAs: (v) => (v ? v : null) })}
      />
      <label className="flex min-h-11 items-center gap-3 font-semibold text-ink">
        <input type="checkbox" className="size-5 accent-cta" {...form.register("generic")} />
        Generic (&quot;any good brand&quot;, no part number)
      </label>
    </div>
  );
}

export const BLANK_PART: PartForm = { description: "", part_type: "", brand: "", brand_kind: "unspecified", part_number: "", quantity: 1, kind: "part", segment: null, generic: false };

function NewPart({ onClose }: { onClose: () => void }) {
  const { draft, touched } = useDraft();
  const router = useRouter();
  const [error, setError] = useState("");
  const form = useForm<PartForm>({ resolver: zodResolver(partSchema), defaultValues: BLANK_PART });
  const submit = form.handleSubmit(async (v) => {
    setError("");
    try {
      const r = await adminApi.saveEdit(draft!.id, "part", "", v, "new part");
      touched();
      router.push(`/parts/${encodeURIComponent(r.key)}?draft=${draft!.id}`);
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title="New part" className="max-w-2xl">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <PartFields form={form} />
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <Button type="submit" size="cta">
          Create part
        </Button>
      </form>
    </Dialog>
  );
}

// ---------------------------------------------------------------- prices

function PricesTab() {
  const { draft, writable, touched } = useDraft();
  const { state, reload } = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.prices(v, s), []));
  const [editing, setEditing] = useState<PriceRow | null>(null);
  const [status, setStatus] = useStatus();
  const secondLook = useCallback(
    (r: PriceRow) =>
      adminApi
        .secondLook(draft!.id, r.key)
        .then(() => {
          setStatus({ kind: "saved", text: `Checked: ${r.part} ${inr(r.price_inr)}` });
          touched();
          reload();
        })
        .catch((e) => setStatus({ kind: "error", text: errorMessage(e) })),
    [draft, reload, setStatus, touched],
  );
  const columns = useMemo<ColumnDef<PriceRow, unknown>[]>(
    () => [
      { id: "part", accessorFn: (r) => r.part ?? "", header: "Part" },
      { accessorKey: "segment", header: "Segment" },
      { id: "price", accessorFn: (r) => r.price_inr, header: "Price", cell: ({ row }) => `${inr(row.original.price_inr)}${row.original.price_max_inr ? `–${inr(row.original.price_max_inr)}` : ""}` },
      { id: "source", accessorFn: (r) => r.supplier || r.source_url, header: "Source", cell: ({ row }) => (row.original.supplier || row.original.source_url || <span className="font-bold text-orange-text">missing</span>) },
      { id: "checked", accessorFn: (r) => r.checked_on ?? "", header: "Checked", cell: ({ row }) => (row.original.checked_on ? date(row.original.checked_on) : <span className="font-bold text-orange-text">no date</span>) },
      {
        id: "flag",
        accessorFn: (r) => (r.flagged ? "second look" : r.missing_source ? "source or date missing" : r.second_look_by ? "checked" : ""),
        header: "Flag",
        cell: ({ row }) =>
          row.original.flagged ? (
            <EditedBadge show label="₹20,000+: second look" />
          ) : row.original.second_look_by ? (
            <span className="text-sm text-success">checked by {row.original.second_look_by}</span>
          ) : row.original.missing_source ? (
            <EditedBadge show label="source or date missing" />
          ) : null,
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) =>
          writable ? (
            <span className="flex flex-wrap gap-2">
              {row.original.flagged && (
                <Button type="button" className="h-10 rounded-full px-3 text-sm font-bold" onClick={() => void secondLook(row.original)}>
                  Second look
                </Button>
              )}
              <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => setEditing(row.original)}>
                Edit
              </Button>
            </span>
          ) : null,
      },
    ],
    [writable, secondLook],
  );
  if (state.kind === "loading") return <p role="status">Loading prices…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  return (
    <>
      <p className="text-ink/80">
        Every price needs a source and the date it was checked. Prices of ₹20,000 or more are flagged until a second person (not the one who entered it)
        checks them.
      </p>
      <SaveStatus status={status} />
      <DataTable
        data={state.data}
        columns={columns}
        caption="Prices"
        searchLabel="Search prices (part, source)"
        filters={[
          { column: "flag", label: "Flag", options: ["second look", "source or date missing", "checked"].map((x) => ({ value: x, label: x })) },
          { column: "segment", label: "Segment", options: SEGMENTS.map((x) => ({ value: x, label: x })) },
        ]}
        pageSize={25}
        getRowId={(r) => r.key}
        csv={{
          filename: `prices-v${draft?.id}`,
          columns: [
            { header: "Part key", value: (r) => r.part_key ?? "" },
            { header: "Part", value: (r) => r.part ?? "" },
            { header: "Segment", value: (r) => r.segment },
            { header: "Price", value: (r) => String(r.price_inr) },
            { header: "Up to", value: (r) => String(r.price_max_inr ?? "") },
            { header: "Supplier", value: (r) => r.supplier },
            { header: "Link", value: (r) => r.source_url },
            { header: "Checked on", value: (r) => r.checked_on ?? "" },
            { header: "Second look by", value: (r) => r.second_look_by ?? "" },
          ],
        }}
      />
      {editing && (
        <PriceDialog
          partKey={editing.part_key!}
          row={editing}
          onClose={() => setEditing(null)}
          onSaved={(warning) => {
            setStatus({ kind: "saved", text: warning ?? "Saved in the draft." });
            setEditing(null);
            reload();
          }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------- labour

function LabourTab() {
  const { draft, writable } = useDraft();
  const { state, reload } = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.labour(v, s), []));
  const [zone, setZone] = useState<ZoneRateRow | null>(null);
  const [labour, setLabour] = useState<LabourRow | "new" | null>(null);
  const [status, setStatus] = useStatus();
  if (state.kind === "loading") return <p role="status">Loading labour rates…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const zones = [...new Map(state.data.zones.map((z) => [z.zone, z.zone_label])).entries()];
  const cell = (code: string, seg: string) => state.data.zones.find((z) => z.zone === code && z.segment === seg)!;
  const done = (text: string) => {
    setStatus({ kind: "saved", text });
    setZone(null);
    setLabour(null);
    reload();
  };
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="zones-heading" className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="zones-heading" className="text-xl font-black text-ink">
            Mechanic labour per hour by zone
          </h2>
          <a href={adminApi.zoneRatesYamlUrl(draft!.id)} className="inline-flex min-h-11 items-center gap-2 font-bold text-orange-text underline underline-offset-4" download="zone_labour_rates.yaml">
            <Download aria-hidden="true" className="size-5" /> Download as zone_labour_rates.yaml
          </a>
        </div>
        <p className="text-ink/80">
          Estimates use hours × the zone&apos;s rate once a rate has a source and a check date; until then, the sheet&apos;s labour. Live after publishing; the
          file download is for committing to the repository.
        </p>
        <SaveStatus status={status} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-xl text-left">
            <caption className="sr-only">Zone labour rates per hour</caption>
            <thead>
              <tr className="border-b-2 border-ink">
                <th scope="col" className="p-2">Zone</th>
                {SEGMENTS.map((s) => (
                  <th key={s} scope="col" className="p-2">
                    {s}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {zones.map(([code, label]) => (
                <tr key={code} className="border-b border-border">
                  <th scope="row" className="p-2 text-left font-semibold">
                    {label}
                  </th>
                  {SEGMENTS.map((s) => {
                    const z = cell(code, s);
                    return (
                      <td key={s} className="p-2 align-top">
                        <span className="flex flex-col gap-1">
                          <span className="font-bold">{z.rate_min_inr ? (z.rate_min_inr === z.rate_max_inr ? inr(z.rate_min_inr) : `${inr(z.rate_min_inr)}–${inr(z.rate_max_inr)}`) : "not known"}</span>
                          {z.source && <span className="text-xs text-ink/70">{z.source} · {z.checked_on && date(z.checked_on)}</span>}
                          <EditedBadge show={z.edit} />
                          {writable && (
                            <Button type="button" variant="outline" className="h-10 self-start rounded-full px-3 text-sm" onClick={() => setZone(z)} aria-label={`Edit ${label} ${s} rate`}>
                              Edit
                            </Button>
                          )}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section aria-labelledby="research-heading" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="research-heading" className="text-xl font-black text-ink">
            Labour research (per repair)
          </h2>
          {writable && (
            <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => setLabour("new")}>
              <Plus aria-hidden="true" className="size-5" /> Add a labour rate
            </Button>
          )}
        </div>
        <DataTable
          data={state.data.research}
          columns={[
            { accessorKey: "repair", header: "Repair" },
            { accessorKey: "segment", header: "Segment" },
            { accessorKey: "city", header: "City" },
            { id: "amount", accessorFn: (r: LabourRow) => r.amount_inr, header: "Amount", cell: ({ row }: { row: { original: LabourRow } }) => inr(row.original.amount_inr) },
            { accessorKey: "basis", header: "Source" },
            { id: "checked", accessorFn: (r: LabourRow) => r.checked_on ?? "", header: "Checked" },
            {
              id: "actions",
              header: "",
              enableSorting: false,
              cell: ({ row }: { row: { original: LabourRow } }) =>
                writable ? (
                  <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => setLabour(row.original)}>
                    Edit
                  </Button>
                ) : null,
            },
          ]}
          caption="Labour research rows"
          searchLabel="Search labour rates"
          pageSize={20}
          getRowId={(r) => r.key}
        />
      </section>
      {zone && <ZoneDialog row={zone} onClose={() => setZone(null)} onSaved={done} />}
      {labour && <LabourDialog row={labour === "new" ? null : labour} onClose={() => setLabour(null)} onSaved={done} />}
    </div>
  );
}

function ZoneDialog({ row, onClose, onSaved }: { row: ZoneRateRow; onClose: () => void; onSaved: (t: string) => void }) {
  const { draft, touched } = useDraft();
  const [error, setError] = useState("");
  const form = useForm<ZoneRateForm>({
    resolver: zodResolver(zoneRateSchema),
    defaultValues: {
      rate_min_inr: row.rate_min_inr ?? (undefined as unknown as number),
      rate_max_inr: row.rate_max_inr ?? (undefined as unknown as number),
      source: row.source,
      checked_on: row.checked_on ?? new Date().toISOString().slice(0, 10),
    },
  });
  const e = form.formState.errors;
  const run = (data: unknown, text: string) =>
    adminApi
      .saveEdit(draft!.id, "zone_rate", row.key, data)
      .then(() => {
        touched();
        onSaved(text);
      })
      .catch((err) => setError(errorMessage(err)));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={`${row.zone_label}: ${row.segment} cars`}>
      <form onSubmit={form.handleSubmit((v) => run(v, `Saved ${row.zone_label} ${row.segment}.`))} className="flex flex-col gap-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="Per hour from (₹)" type="number" error={e.rate_min_inr} {...form.register("rate_min_inr", { valueAsNumber: true })} />
          <TextInput label="Per hour up to (₹)" type="number" error={e.rate_max_inr} {...form.register("rate_max_inr", { valueAsNumber: true })} />
        </div>
        <TextInput label="Source (e.g. 5 garages in Sector 14-56, phone survey)" error={e.source} {...form.register("source")} />
        <TextInput label="Checked on" type="date" error={e.checked_on} {...form.register("checked_on")} />
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" size="cta">
            Save in draft
          </Button>
          {row.rate_min_inr !== null && (
            <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base" onClick={() => void run(null, `Cleared ${row.zone_label} ${row.segment}.`)}>
              Clear (not known)
            </Button>
          )}
        </div>
      </form>
    </Dialog>
  );
}

function LabourDialog({ row, onClose, onSaved }: { row: LabourRow | null; onClose: () => void; onSaved: (t: string) => void }) {
  const { draft, touched } = useDraft();
  const [error, setError] = useState("");
  const form = useForm<LabourForm>({
    resolver: zodResolver(labourSchema),
    defaultValues: {
      repair: row?.repair ?? "",
      segment: (row?.segment as LabourForm["segment"]) ?? "budget",
      city: row?.city ?? "Delhi NCR",
      amount_inr: row?.amount_inr ?? (undefined as unknown as number),
      workshop_type: row?.workshop_type ?? "",
      basis: row?.basis ?? "",
      status: (row?.status as LabourForm["status"]) ?? "approx",
      checked_on: row?.checked_on ?? new Date().toISOString().slice(0, 10),
    },
  });
  const e = form.formState.errors;
  const submit = form.handleSubmit(async ({ repair, segment, city, ...data }) => {
    setError("");
    try {
      await adminApi.saveEdit(draft!.id, "labour_rate", row ? row.key : `${repair}|${segment}|${city}`, data);
      touched();
      onSaved(`Saved labour for ${repair}.`);
    } catch (err) {
      setError(errorMessage(err));
    }
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={row ? "Edit labour rate" : "Add a labour rate"} className="max-w-2xl">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="Repair" disabled={!!row} error={e.repair} {...form.register("repair")} />
          <Select label="Segment" disabled={!!row} options={SEGMENTS.map((x) => ({ value: x, label: x }))} {...form.register("segment")} />
          <TextInput label="City" disabled={!!row} error={e.city} {...form.register("city")} />
          <TextInput label="Amount (₹)" type="number" error={e.amount_inr} {...form.register("amount_inr", { valueAsNumber: true })} />
          <TextInput label="Workshop type" error={e.workshop_type} {...form.register("workshop_type")} />
          <Select label="Status" options={[{ value: "approx", label: "approx" }, { value: "listed", label: "listed" }]} {...form.register("status")} />
          <TextInput label="Source (who quoted it, where)" error={e.basis} className="sm:col-span-2" {...form.register("basis")} />
          <TextInput label="Checked on" type="date" error={e.checked_on} {...form.register("checked_on")} />
        </div>
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <Button type="submit" size="cta">
          Save in draft
        </Button>
      </form>
    </Dialog>
  );
}

// ---------------------------------------------------------------- CSV import

function ImportTab() {
  const { draft, writable, touched } = useDraft();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [status, setStatus] = useStatus();
  const [busy, setBusy] = useState(false);
  async function run(commit: boolean) {
    if (!file) return;
    setBusy(true);
    try {
      const r = await adminApi.importPrices(draft!.id, file, commit);
      setPreview(r);
      if (commit) {
        touched();
        setStatus({ kind: "saved", text: `Imported ${r.summary.valid} rows into draft v${draft!.id}.` });
      } else setStatus({ kind: "idle" });
    } catch (e) {
      setStatus({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Import prices from a CSV file" className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-4">
      <p className="text-ink/80">
        One row per price: the part (new parts are created), its segment price with source and check date and, optionally, the car it fits. Check the file
        first; nothing is saved until you import. {" "}
        <a href={adminApi.csvTemplateUrl()} className="font-bold text-orange-text underline underline-offset-4" download="price-import-template.csv">
          Download the template
        </a>
      </p>
      <label className="flex flex-col gap-1 font-semibold text-ink">
        CSV file
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setPreview(null);
          }}
          className="min-h-12 rounded-xl border border-input bg-white px-4 py-2.5 text-base text-ink file:mr-3 file:rounded-full file:border-0 file:bg-warm-white file:px-4 file:py-1 file:font-bold"
        />
      </label>
      <div className="flex flex-wrap gap-3">
        <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base" disabled={!file || busy} onClick={() => void run(false)}>
          Check the file
        </Button>
        {writable && preview && preview.summary.valid > 0 && (
          <Button type="button" size="cta" disabled={busy} onClick={() => void run(true)}>
            Import {preview.summary.valid} valid rows into draft v{draft?.id}
          </Button>
        )}
      </div>
      <SaveStatus status={status} />
      {preview && (
        <div className="flex flex-col gap-2" data-testid="import-preview">
          <p className="font-bold text-ink">
            {preview.summary.rows} rows · {preview.summary.valid} valid · {preview.summary.errors} with errors · {preview.summary.flagged} of ₹20,000 or more (second
            look)
          </p>
          <ul className="flex flex-col gap-1 text-sm">
            {preview.rows.map((r) => (
              <li key={r.line} className={cn("rounded-xl p-2", r.errors.length ? "bg-amber-bg text-amber-text" : "bg-warm-white text-ink")}>
                Line {r.line}: {r.row.description || "(no description)"} · {r.row.segment} · {r.row.price_inr}
                {r.flagged && " · second look"}
                {r.errors.length > 0 && <span className="block font-semibold">{r.errors.join("; ")}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export { inr };
