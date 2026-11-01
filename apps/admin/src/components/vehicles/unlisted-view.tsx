"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import { Button } from "@im/ui/button";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { Checkbox, numberOrNull, SaveStatus, Select, TextInput, useStatus } from "@/components/form";
import { useMe } from "@/components/staff-shell";
import { adminApi, errorMessage, type UnlistedCar } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { type AddCarForm, addCarSchema, FUELS, SEGMENTS, TRANSMISSIONS } from "@/lib/schemas";

/** Cars customers typed because they were not in the catalogue: add each to the catalogue (live) or dismiss it. */
export function UnlistedView() {
  const { me } = useMe();
  const canManage = me.permissions.includes("vehicles.manage");
  const [rows, setRows] = useState<UnlistedCar[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [adding, setAdding] = useState<UnlistedCar | null>(null);
  const [status, setStatus] = useStatus();
  useEffect(() => {
    const ctrl = new AbortController();
    adminApi
      .unlisted(ctrl.signal)
      .then(setRows)
      .catch((e) => !ctrl.signal.aborted && setError(errorMessage(e)));
    return () => ctrl.abort();
  }, [attempt]);
  const reload = () => setAttempt((a) => a + 1);

  const columns = useMemo<ColumnDef<UnlistedCar, unknown>[]>(
    () => [
      { id: "typed", accessorFn: (u) => u.raw_text || `${u.typed_make ?? ""} ${u.typed_model ?? ""} ${u.typed_year ?? ""}`.trim(), header: "Typed" },
      { id: "fuel", accessorFn: (u) => u.fuel ?? "not sure", header: "Fuel" },
      { id: "gearbox", accessorFn: (u) => u.transmission ?? "not sure", header: "Gearbox" },
      { id: "segment", accessorFn: (u) => u.price_segment ?? "not sure", header: "Price" },
      { accessorKey: "sessions", header: "Diagnoses" },
      { accessorKey: "created_at", header: "When", cell: ({ row }) => dateTime(row.original.created_at) },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) =>
          canManage ? (
            <span className="flex flex-wrap gap-2">
              <Button type="button" className="h-11 rounded-full px-4 text-base font-bold" onClick={() => setAdding(row.original)}>
                Add to catalogue
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-11 rounded-full px-4 text-base"
                onClick={() =>
                  adminApi
                    .dismissUnlisted(row.original.id)
                    .then(() => {
                      setStatus({ kind: "saved", text: "Dismissed." });
                      reload();
                    })
                    .catch((e) => setStatus({ kind: "error", text: errorMessage(e) }))
                }
              >
                Dismiss
              </Button>
            </span>
          ) : null,
      },
    ],
    [canManage, setStatus],
  );

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!rows) return <p role="status">Loading unlisted cars…</p>;
  return (
    <section aria-labelledby="unlisted-heading" className="flex flex-col gap-3">
      <h2 id="unlisted-heading" className="text-2xl font-black text-ink">
        Unlisted cars ({rows.length})
      </h2>
      <p className="text-ink/80">
        The car catalogue is not part of the dataset versions: a car you add is in the car picker at once (audited). The full catalogue editor comes
        in part 2.
      </p>
      <SaveStatus status={status} />
      <DataTable data={rows} columns={columns} caption="Unlisted cars waiting for review" searchLabel="Search typed cars" pageSize={20} getRowId={(u) => String(u.id)} empty="No cars waiting." />
      {adding && (
        <AddDialog
          car={adding}
          onClose={() => setAdding(null)}
          onDone={(created) => {
            setStatus({ kind: "saved", text: created.length ? `Added: ${created.join(", ")}` : "Already in the catalogue: marked reviewed." });
            reload();
          }}
        />
      )}
    </section>
  );
}

function AddDialog({ car, onClose, onDone }: { car: UnlistedCar; onClose: () => void; onDone: (created: string[]) => void }) {
  const [error, setError] = useState("");
  const [makes, setMakes] = useState<{ name: string; models: string[] }[]>([]);
  useEffect(() => {
    adminApi.makes().then(setMakes).catch(() => undefined);
  }, []);
  const form = useForm<AddCarForm>({
    resolver: zodResolver(addCarSchema),
    defaultValues: {
      make: car.typed_make ?? "",
      model: car.typed_model ?? "",
      body: "",
      year_from: car.typed_year ?? new Date().getFullYear(),
      year_to: null,
      fuel: (car.fuel as AddCarForm["fuel"]) ?? "petrol",
      transmissions: car.transmission ? [car.transmission as AddCarForm["transmissions"][number]] : ["mt"],
      price_segment: (car.price_segment as AddCarForm["price_segment"]) ?? "budget",
      engine: "",
    },
  });
  const errors = form.formState.errors;
  const make = useWatch({ control: form.control, name: "make" });
  const known = makes.find((m) => m.name.toLowerCase() === make.trim().toLowerCase());
  const submit = form.handleSubmit(async (v) => {
    setError("");
    try {
      const r = await adminApi.addUnlisted(car.id, { ...v, body: v.body || null });
      onDone(r.created);
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={`Add “${car.raw_text || `${car.typed_make} ${car.typed_model}`}”`} className="max-w-2xl">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="Make" list="makes" error={errors.make} hint={known ? "Existing make" : make ? "A new make" : undefined} {...form.register("make")} />
          <TextInput label="Model" list="models" error={errors.model} {...form.register("model")} />
          <datalist id="makes">
            {makes.map((m) => (
              <option key={m.name} value={m.name} />
            ))}
          </datalist>
          <datalist id="models">
            {known?.models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <TextInput label="First year" type="number" error={errors.year_from} {...form.register("year_from", { valueAsNumber: true })} />
          <TextInput label="Last year (empty = still sold)" type="number" error={errors.year_to} {...form.register("year_to", { setValueAs: numberOrNull })} />
          <Select label="Fuel" options={FUELS.map((f) => ({ value: f, label: f }))} {...form.register("fuel")} />
          <Select label="Price segment" options={SEGMENTS.map((s) => ({ value: s, label: s }))} hint="budget below 10 lakh, mid 10-25 lakh, premium above 25 lakh" {...form.register("price_segment")} />
          <TextInput label="Body type" error={errors.body} {...form.register("body")} />
          <TextInput label="Engine label (optional)" error={errors.engine} {...form.register("engine")} />
        </div>
        <fieldset className="flex flex-wrap gap-x-4">
          <legend className="font-semibold text-ink">Gearboxes (one variant each)</legend>
          {TRANSMISSIONS.map((t) => (
            <Checkbox key={t} label={t} value={t} {...form.register("transmissions")} />
          ))}
        </fieldset>
        {errors.transmissions?.message && <p className="text-sm font-semibold text-orange-text">{errors.transmissions.message}</p>}
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <Button type="submit" size="cta" disabled={form.formState.isSubmitting}>
          Add to catalogue
        </Button>
      </form>
    </Dialog>
  );
}
