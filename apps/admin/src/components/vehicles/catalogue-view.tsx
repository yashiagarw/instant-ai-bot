"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { Plus } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { EditedBadge, numberOrNull, SaveStatus, Select, TextInput, useStatus } from "@/components/form";
import { useMe } from "@/components/staff-shell";
import { adminApi, type CatGeneration, type Catalogue, type CatMake, type CatModel, type CatVariant, errorMessage } from "@/lib/api";
import { FUELS, generationSchema, makeSchema, modelSchema, SEGMENTS, TRANSMISSIONS, type VariantForm, variantSchema } from "@/lib/schemas";

type Kind = "makes" | "models" | "generations" | "variants";
type Editing =
  | { kind: "makes"; row: CatMake | null }
  | { kind: "models"; row: CatModel | null; make: CatMake }
  | { kind: "generations"; row: CatGeneration | null; model: CatModel }
  | { kind: "variants"; row: CatVariant | null; model: CatModel };

/** The car catalogue: makes, models, generations and variants. Live at once (not part of the dataset versions) and
 * audited; rows changed here are kept by `python -m app.vehicles.seed`. */
export function CatalogueView() {
  const { me } = useMe();
  const canManage = me.permissions.includes("vehicles.manage");
  const [data, setData] = useState<Catalogue | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((a) => a + 1), []);
  const [makeId, setMakeId] = useState<number | null>(null);
  const [modelId, setModelId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [status, setStatus] = useStatus();

  useEffect(() => {
    const ctrl = new AbortController();
    adminApi
      .catalogue(ctrl.signal)
      .then(setData)
      .catch((e) => !ctrl.signal.aborted && setError(errorMessage(e)));
    return () => ctrl.abort();
  }, [attempt]);

  const make = data?.makes.find((m) => m.id === makeId) ?? null;
  const model = make?.models.find((m) => m.id === modelId) ?? null;

  async function remove(kind: Kind, id: number, what: string) {
    try {
      await adminApi.deleteVehicle(kind, id);
      setStatus({ kind: "saved", text: `Deleted ${what}.` });
      if (kind === "makes") setMakeId(null);
      if (kind === "models") setModelId(null);
      reload();
    } catch (e) {
      setStatus({ kind: "error", text: errorMessage(e) });
    }
  }

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <p role="status">Loading the catalogue…</p>;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-ink/80">
        Changes are live at once for new diagnoses and are written to the audit log. The vehicle seed (vehicles.yaml) keeps rows changed here.
      </p>
      <SaveStatus status={status} />
      <div className="grid gap-4 lg:grid-cols-[minmax(14rem,1fr)_minmax(14rem,1fr)_2fr]">
        <Column
          title="Makes"
          add={canManage ? () => setEditing({ kind: "makes", row: null }) : undefined}
          items={data.makes.map((m) => ({ id: m.id, label: m.name, sub: `${m.models.length} models`, edited: m.edited_by }))}
          selected={makeId}
          onSelect={(id) => {
            setMakeId(id);
            setModelId(null);
          }}
        />
        {make ? (
          <Column
            title={`${make.name} models`}
            add={canManage ? () => setEditing({ kind: "models", row: null, make }) : undefined}
            items={make.models.map((m) => ({ id: m.id, label: m.name, sub: `${m.variants.length} variants${m.body_type ? ` · ${m.body_type}` : ""}`, edited: m.edited_by }))}
            selected={modelId}
            onSelect={setModelId}
            actions={
              canManage && (
                <span className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" className="h-10 rounded-full px-4 text-sm" onClick={() => setEditing({ kind: "makes", row: make })}>
                    Edit make
                  </Button>
                  <Button type="button" variant="outline" className="h-10 rounded-full px-4 text-sm" onClick={() => void remove("makes", make.id, make.name)}>
                    Delete make
                  </Button>
                </span>
              )
            }
          />
        ) : (
          <p className="text-ink/70">Choose a make.</p>
        )}
        {model && make ? (
          <ModelPanel
            make={make}
            model={model}
            canManage={canManage}
            onEdit={setEditing}
            onDelete={remove}
          />
        ) : (
          make && <p className="text-ink/70">Choose a model.</p>
        )}
      </div>
      {editing && (
        <EditDialog
          editing={editing}
          features={data.features}
          onClose={() => setEditing(null)}
          onSaved={(text) => {
            setStatus({ kind: "saved", text });
            setEditing(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

function Column({
  title,
  items,
  selected,
  onSelect,
  add,
  actions,
}: {
  title: string;
  items: { id: number; label: string; sub: string; edited: string | null }[];
  selected: number | null;
  onSelect: (id: number) => void;
  add?: () => void;
  actions?: React.ReactNode;
}) {
  const [q, setQ] = useState("");
  const shown = items.filter((i) => i.label.toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <section aria-label={title} className="flex min-w-0 flex-col gap-2 rounded-3xl border border-border bg-white p-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-black text-ink">{title}</h2>
        {add && (
          <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={add}>
            <Plus aria-hidden="true" className="size-4" /> Add
          </Button>
        )}
      </div>
      {actions}
      <TextInput label={`Search ${title.toLowerCase()}`} value={q} onChange={(e) => setQ(e.target.value)} />
      <ul className="flex max-h-96 flex-col overflow-y-auto">
        {shown.map((i) => (
          <li key={i.id}>
            <button
              type="button"
              aria-pressed={selected === i.id}
              onClick={() => onSelect(i.id)}
              className={cn(
                "flex min-h-11 w-full flex-col items-start rounded-xl px-3 py-1.5 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring",
                selected === i.id ? "bg-ink text-white" : "hover:bg-warm-white",
              )}
            >
              <span className="font-semibold">{i.label}</span>
              <span className={cn("text-xs", selected === i.id ? "text-white/80" : "text-ink/70")}>
                {i.sub}
                {i.edited && ` · edited by ${i.edited}`}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ModelPanel({
  make,
  model,
  canManage,
  onEdit,
  onDelete,
}: {
  make: CatMake;
  model: CatModel;
  canManage: boolean;
  onEdit: (e: Editing) => void;
  onDelete: (kind: Kind, id: number, what: string) => void;
}) {
  const gens = useMemo(() => Object.fromEntries(model.generations.map((g) => [g.id, g.name])), [model.generations]);
  const columns = useMemo<ColumnDef<CatVariant, unknown>[]>(
    () => [
      { accessorKey: "name", header: "Variant", cell: ({ row }) => <span className="flex items-center gap-2">{row.original.name} <EditedBadge show={row.original.edited_by} label="Edited here" /></span> },
      { id: "generation", accessorFn: (v) => (v.generation_id ? gens[v.generation_id] : ""), header: "Generation" },
      { accessorKey: "price_segment", header: "Segment" },
      { id: "features", accessorFn: (v) => Object.entries(v.features).map(([k, x]) => `${k}: ${x ? "yes" : "no"}`).join(", "), header: "Features" },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) =>
          canManage ? (
            <span className="flex gap-2">
              <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => onEdit({ kind: "variants", row: row.original, model })}>
                Edit
              </Button>
              <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => onDelete("variants", row.original.id, row.original.name)}>
                Delete
              </Button>
            </span>
          ) : null,
      },
    ],
    [canManage, gens, model, onEdit, onDelete],
  );
  return (
    <section aria-label={`${make.name} ${model.name}`} className="flex min-w-0 flex-col gap-3 rounded-3xl border border-border bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-black text-ink">
          {make.name} {model.name}
        </h2>
        {canManage && (
          <span className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => onEdit({ kind: "models", row: model, make })}>
              Edit model
            </Button>
            <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => onDelete("models", model.id, model.name)}>
              Delete model
            </Button>
          </span>
        )}
      </div>
      <h3 className="font-bold text-ink">Generations</h3>
      <ul className="flex flex-col gap-1">
        {model.generations.length === 0 && <li className="text-ink/70">None yet.</li>}
        {model.generations.map((g) => (
          <li key={g.id} className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {g.name} ({g.year_from}–{g.year_to ?? "now"})
            </span>
            {canManage && (
              <span className="flex gap-2">
                <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => onEdit({ kind: "generations", row: g, model })}>
                  Edit
                </Button>
                <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => onDelete("generations", g.id, g.name)}>
                  Delete
                </Button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {canManage && (
        <span className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => onEdit({ kind: "generations", row: null, model })}>
            <Plus aria-hidden="true" className="size-4" /> Add generation
          </Button>
          <Button type="button" className="h-10 rounded-full px-3 text-sm font-bold" onClick={() => onEdit({ kind: "variants", row: null, model })}>
            <Plus aria-hidden="true" className="size-4" /> Add variant
          </Button>
        </span>
      )}
      <DataTable data={model.variants} columns={columns} caption={`${model.name} variants`} searchLabel="Search variants" pageSize={15} getRowId={(v) => String(v.id)} empty="No variants." />
    </section>
  );
}

function EditDialog({ editing, features, onClose, onSaved }: { editing: Editing; features: Record<string, string>; onClose: () => void; onSaved: (text: string) => void }) {
  const title = `${editing.row ? "Edit" : "Add"} ${editing.kind.slice(0, -1)}`;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={title} className="max-w-2xl">
      {editing.kind === "makes" && <MakeForm editing={editing} onSaved={onSaved} />}
      {editing.kind === "models" && <ModelForm editing={editing} onSaved={onSaved} />}
      {editing.kind === "generations" && <GenerationForm editing={editing} onSaved={onSaved} />}
      {editing.kind === "variants" && <VariantFormView editing={editing} features={features} onSaved={onSaved} />}
    </Dialog>
  );
}

function useSave(onSaved: (text: string) => void) {
  const [error, setError] = useState("");
  const save = async (kind: Kind, id: number | null, body: unknown, what: string) => {
    setError("");
    try {
      await adminApi.saveVehicle(kind, id, body);
      onSaved(`Saved ${what}.`);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const errorLine = error ? (
    <p role="alert" className="font-semibold text-orange-text">
      {error}
    </p>
  ) : null;
  return { save, errorLine };
}

function MakeForm({ editing, onSaved }: { editing: Extract<Editing, { kind: "makes" }>; onSaved: (t: string) => void }) {
  const { save, errorLine } = useSave(onSaved);
  const form = useForm<z.infer<typeof makeSchema>>({ resolver: zodResolver(makeSchema), defaultValues: { name: editing.row?.name ?? "", aliases: editing.row?.aliases ?? "" } });
  const e = form.formState.errors;
  return (
    <form onSubmit={form.handleSubmit((v) => save("makes", editing.row?.id ?? null, v, v.name))} className="flex flex-col gap-4" noValidate>
      <TextInput label="Name" error={e.name} {...form.register("name")} />
      <TextInput label="Other words people type (space separated)" error={e.aliases} {...form.register("aliases")} />
      {errorLine}
      <Button type="submit" size="cta">
        Save make
      </Button>
    </form>
  );
}

function ModelForm({ editing, onSaved }: { editing: Extract<Editing, { kind: "models" }>; onSaved: (t: string) => void }) {
  const { save, errorLine } = useSave(onSaved);
  const form = useForm<z.infer<typeof modelSchema>>({
    resolver: zodResolver(modelSchema),
    defaultValues: { name: editing.row?.name ?? "", body_type: editing.row?.body_type ?? "", aliases: editing.row?.aliases ?? "" },
  });
  const e = form.formState.errors;
  return (
    <form
      onSubmit={form.handleSubmit((v) => save("models", editing.row?.id ?? null, { ...v, body_type: v.body_type || null, make_id: editing.make.id }, v.name))}
      className="flex flex-col gap-4"
      noValidate
    >
      <TextInput label="Name" error={e.name} {...form.register("name")} />
      <TextInput label="Body type (hatchback, sedan, SUV ...)" error={e.body_type} {...form.register("body_type")} />
      <TextInput label="Other words people type (space separated)" error={e.aliases} {...form.register("aliases")} />
      {errorLine}
      <Button type="submit" size="cta">
        Save model
      </Button>
    </form>
  );
}

function GenerationForm({ editing, onSaved }: { editing: Extract<Editing, { kind: "generations" }>; onSaved: (t: string) => void }) {
  const { save, errorLine } = useSave(onSaved);
  const form = useForm<z.infer<typeof generationSchema>>({
    resolver: zodResolver(generationSchema),
    defaultValues: { name: editing.row?.name ?? "", year_from: editing.row?.year_from ?? new Date().getFullYear(), year_to: editing.row?.year_to ?? null },
  });
  const e = form.formState.errors;
  return (
    <form onSubmit={form.handleSubmit((v) => save("generations", editing.row?.id ?? null, { ...v, model_id: editing.model.id }, v.name))} className="flex flex-col gap-4" noValidate>
      <TextInput label="Name (e.g. 3rd gen)" error={e.name} {...form.register("name")} />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextInput label="First year" type="number" error={e.year_from} {...form.register("year_from", { valueAsNumber: true })} />
        <TextInput label="Last year (empty = still sold)" type="number" error={e.year_to} {...form.register("year_to", { setValueAs: numberOrNull })} />
      </div>
      {errorLine}
      <Button type="submit" size="cta">
        Save generation
      </Button>
    </form>
  );
}

const tri = (v: boolean | undefined) => (v === true ? "yes" : v === false ? "no" : "unknown");

function VariantFormView({ editing, features, onSaved }: { editing: Extract<Editing, { kind: "variants" }>; features: Record<string, string>; onSaved: (t: string) => void }) {
  const { save, errorLine } = useSave(onSaved);
  const r = editing.row;
  const form = useForm<VariantForm>({
    resolver: zodResolver(variantSchema),
    defaultValues: {
      generation_id: r?.generation_id ?? null,
      fuel: (r?.fuel as VariantForm["fuel"]) ?? "petrol",
      transmission: (r?.transmission as VariantForm["transmission"]) ?? "mt",
      engine: r?.engine ?? "",
      year_from: r?.year_from ?? new Date().getFullYear(),
      year_to: r?.year_to ?? null,
      price_segment: (r?.price_segment as VariantForm["price_segment"]) ?? "budget",
      features: Object.fromEntries(Object.keys(features).map((k) => [k, tri(r?.features[k])])),
    },
  });
  const e = form.formState.errors;
  const submit = form.handleSubmit((v) => {
    const feats = Object.fromEntries(Object.entries(v.features).filter(([, x]) => x !== "unknown").map(([k, x]) => [k, x === "yes"]));
    return save("variants", r?.id ?? null, { ...v, features: feats, model_id: editing.model.id }, `${editing.model.name} variant`);
  });
  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <Select label="Fuel" options={FUELS.map((f) => ({ value: f, label: f }))} {...form.register("fuel")} />
        <Select label="Gearbox" options={TRANSMISSIONS.map((t) => ({ value: t, label: t }))} {...form.register("transmission")} />
        <TextInput label="First year" type="number" error={e.year_from} {...form.register("year_from", { valueAsNumber: true })} />
        <TextInput label="Last year (empty = still sold)" type="number" error={e.year_to} {...form.register("year_to", { setValueAs: numberOrNull })} />
        <Select label="Price segment" hint="budget below 10 lakh, mid 10-25 lakh, premium above 25 lakh" options={SEGMENTS.map((s) => ({ value: s, label: s }))} {...form.register("price_segment")} />
        <TextInput label="Engine label (optional)" error={e.engine} {...form.register("engine")} />
        <Select
          label="Generation"
          options={[{ value: "", label: "None" }, ...editing.model.generations.map((g) => ({ value: String(g.id), label: g.name }))]}
          {...form.register("generation_id", { setValueAs: numberOrNull })}
        />
      </div>
      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="mb-1 font-semibold text-ink">Features (unknown never changes a ranking)</legend>
        {Object.entries(features).map(([k, label]) => (
          <Select key={k} label={label} options={["unknown", "yes", "no"].map((x) => ({ value: x, label: x }))} {...form.register(`features.${k}` as const)} />
        ))}
      </fieldset>
      {errorLine}
      <Button type="submit" size="cta">
        Save variant
      </Button>
    </form>
  );
}
