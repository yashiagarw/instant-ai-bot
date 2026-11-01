"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import type { z } from "zod";
import { Plus } from "lucide-react";

import { Button } from "@im/ui/button";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { Checkbox, EditedBadge, numberOrNull, Select, TextInput } from "@/components/form";
import { useDraft, useDraftData } from "@/components/knowledge/draft";
import { adminApi, errorMessage, type Taxonomy } from "@/lib/api";
import { type CategoryForm, categorySchema, filterSchema, FUELS, type GroupForm, groupSchema, TRANSMISSIONS } from "@/lib/schemas";

type Group = Taxonomy["groups"][number];
type Category = Taxonomy["categories"][number];
type Filter = Taxonomy["vehicle_filters"][number];

/** Tiles, the emergency row, the inspection booking, categories and vehicle filters (replaces editing taxonomy.yaml). */
export function TaxonomyTab() {
  const { writable } = useDraft();
  const { state, reload } = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.taxonomy(v, s), []));
  const [group, setGroup] = useState<Group | "tile" | "emergency" | null>(null);
  const [category, setCategory] = useState<Category | null>(null);
  const [filter, setFilter] = useState<Filter | "new" | null>(null);
  if (state.kind === "loading") return <p role="status">Loading tiles and categories…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const tax = state.data;
  const sections: [string, Group["group_type"]][] = [
    ["Problem tiles", "tile"],
    ["Emergency row", "emergency"],
    ["Inspection booking", "inspection"],
  ];
  return (
    <div className="flex flex-col gap-6">
      {sections.map(([title, type]) => (
        <section key={type} aria-labelledby={`tax-${type}`} className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id={`tax-${type}`} className="text-xl font-black text-ink">
              {title}
            </h2>
            {writable && type !== "inspection" && (
              <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => setGroup(type)}>
                <Plus aria-hidden="true" className="size-5" /> {type === "tile" ? "New tile" : "New emergency topic"}
              </Button>
            )}
          </div>
          <ol className="flex flex-col divide-y divide-border">
            {tax.groups
              .filter((g) => g.group_type === type)
              .map((g) => (
                <li key={g.code} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="flex flex-col">
                    <span className="font-bold text-ink">
                      {g.label_en} <span lang="hi">· {g.label_hi}</span> <EditedBadge show={g.edit} />
                    </span>
                    <span className="text-sm text-ink/75">
                      {g.code} · {g.categories.join(", ") || "no categories"}
                      {!g.hi_reviewed && " · Hindi label not checked"}
                    </span>
                  </span>
                  {writable && (
                    <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => setGroup(g)}>
                      Edit
                    </Button>
                  )}
                </li>
              ))}
          </ol>
        </section>
      ))}

      <section aria-labelledby="tax-categories" className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:p-5">
        <h2 id="tax-categories" className="text-xl font-black text-ink">
          Categories
        </h2>
        <ul className="flex flex-col divide-y divide-border">
          {tax.categories.map((c) => (
            <li key={c.code} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="flex flex-col">
                <span className="font-bold text-ink">
                  {c.name} {c.beta && <span className="rounded-full bg-warm-white px-2 text-xs">Beta</span>} <EditedBadge show={c.edit} />
                </span>
                <span className="text-sm text-ink/75">
                  {c.code} · {c.kind} · wave {c.wave} · filters: {c.filters.join(", ") || "none"}
                  {Object.values(c.config).some((x) => x !== null) &&
                    " · engine: " +
                      Object.entries(c.config)
                        .filter(([, x]) => x !== null)
                        .map(([k, x]) => `${k} ${x}`)
                        .join(", ")}
                </span>
              </span>
              {writable && (
                <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => setCategory(c)}>
                  Edit
                </Button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="tax-filters" className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="tax-filters" className="text-xl font-black text-ink">
            Vehicle filters
          </h2>
          {writable && (
            <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => setFilter("new")}>
              <Plus aria-hidden="true" className="size-5" /> New filter
            </Button>
          )}
        </div>
        <ul className="flex flex-col divide-y divide-border">
          {tax.vehicle_filters.map((f) => (
            <li key={f.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="text-ink">
                <strong>{f.name}</strong>: {[...f.fuel, ...f.transmission].join(", ")} <EditedBadge show={f.edit} />
              </span>
              {writable && (
                <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => setFilter(f)}>
                  Edit
                </Button>
              )}
            </li>
          ))}
        </ul>
      </section>

      {group && <GroupDialog group={typeof group === "string" ? null : group} newType={typeof group === "string" ? group : null} tax={tax} onClose={() => setGroup(null)} onSaved={reload} />}
      {category && <CategoryDialog category={category} tax={tax} onClose={() => setCategory(null)} onSaved={reload} />}
      {filter && <FilterDialog filter={filter === "new" ? null : filter} onClose={() => setFilter(null)} onSaved={reload} />}
    </div>
  );
}

function useSave(onSaved: () => void, onClose: () => void) {
  const { draft, touched } = useDraft();
  const [error, setError] = useState("");
  async function save(entity: string, key: string, data: unknown) {
    setError("");
    try {
      await adminApi.saveEdit(draft!.id, entity, key, data);
      touched();
      onSaved();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  return { save, error };
}

function ErrorLine({ error }: { error: string }) {
  return error ? (
    <p role="alert" className="font-semibold text-orange-text">
      {error}
    </p>
  ) : null;
}

function CategoryBoxes({ tax, selected, onChange, legend }: { tax: Taxonomy; selected: string[]; onChange: (v: string[]) => void; legend: string }) {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="font-semibold text-ink">{legend}</legend>
      <div className="grid max-h-56 gap-1 overflow-y-auto rounded-xl border border-border p-2 sm:grid-cols-2">
        {tax.categories.map((c) => (
          <Checkbox
            key={c.code}
            label={c.name}
            checked={selected.includes(c.code)}
            onChange={(e) => onChange(e.target.checked ? [...selected, c.code] : selected.filter((x) => x !== c.code))}
          />
        ))}
      </div>
    </fieldset>
  );
}

function GroupDialog({ group, newType, tax, onClose, onSaved }: { group: Group | null; newType: "tile" | "emergency" | null; tax: Taxonomy; onClose: () => void; onSaved: () => void }) {
  const { save, error } = useSave(onSaved, onClose);
  const form = useForm<GroupForm>({
    resolver: zodResolver(groupSchema),
    defaultValues: group
      ? { code: group.code, group_type: group.group_type, label_en: group.label_en, label_hi: group.label_hi, hi_reviewed: group.hi_reviewed, categories: group.categories, position: group.position }
      : { code: "", group_type: newType!, label_en: "", label_hi: "", hi_reviewed: false, categories: [], position: 99 },
  });
  const errors = form.formState.errors;
  const cats = useWatch({ control: form.control, name: "categories" });
  const submit = form.handleSubmit(({ code, ...v }) => save("group", code, { ...v, variants: group?.variants ?? [] }));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={group ? `Edit ${group.label_en}` : newType === "tile" ? "New tile" : "New emergency topic"} className="max-w-2xl">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {!group && <TextInput label="Code (stable, never changes)" error={errors.code} {...form.register("code")} />}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="English label" error={errors.label_en} {...form.register("label_en")} />
          <TextInput label="Hindi label" lang="hi" error={errors.label_hi} {...form.register("label_hi")} />
        </div>
        <Checkbox label="The Hindi label was checked by a Hindi speaker" {...form.register("hi_reviewed")} />
        {group?.group_type !== "inspection" && (
          <TextInput label="Position (0 = first)" type="number" error={errors.position} {...form.register("position", { valueAsNumber: true })} />
        )}
        <CategoryBoxes tax={tax} selected={cats} onChange={(v) => form.setValue("categories", v, { shouldDirty: true })} legend="Categories behind it" />
        <ErrorLine error={error} />
        <div className="flex flex-wrap gap-3">
          <Button type="submit" size="cta">
            Save in draft
          </Button>
          {group && group.group_type !== "inspection" && (
            <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base" onClick={() => void save("group", group.code, null)}>
              Remove {group.group_type === "tile" ? "tile" : "topic"}
            </Button>
          )}
        </div>
      </form>
    </Dialog>
  );
}

function CategoryDialog({ category, tax, onClose, onSaved }: { category: Category; tax: Taxonomy; onClose: () => void; onSaved: () => void }) {
  const { save, error } = useSave(onSaved, onClose);
  const form = useForm<CategoryForm>({
    resolver: zodResolver(categorySchema),
    defaultValues: { name: category.name, kind: category.kind, beta: category.beta, wave: category.wave, filters: category.filters, config: category.config },
  });
  const errors = form.formState.errors;
  const filters = useWatch({ control: form.control, name: "filters" });
  const submit = form.handleSubmit((v) => save("category", category.code, v));
  const num = { setValueAs: numberOrNull };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={`Edit category ${category.code}`} className="max-w-2xl">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <TextInput label="Name" error={errors.name} {...form.register("name")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Kind"
            options={[
              { value: "diagnose", label: "diagnose (questions, ranked causes)" },
              { value: "fast_track", label: "fast_track (roadside help)" },
              { value: "inspect", label: "inspect (checklist)" },
            ]}
            {...form.register("kind")}
          />
          <TextInput label="Rollout wave" type="number" step="0.5" error={errors.wave} {...form.register("wave", { valueAsNumber: true })} />
        </div>
        <Checkbox label="Beta (shown with a Beta label)" {...form.register("beta")} />
        <fieldset className="flex flex-col gap-1">
          <legend className="font-semibold text-ink">Vehicle filters (all must match; none = every car)</legend>
          <div className="grid gap-1 sm:grid-cols-2">
            {tax.vehicle_filters.map((f) => (
              <Checkbox
                key={f.name}
                label={`${f.name} (${[...f.fuel, ...f.transmission].join(", ")})`}
                checked={filters.includes(f.name)}
                onChange={(e) => form.setValue("filters", e.target.checked ? [...filters, f.name] : filters.filter((x) => x !== f.name), { shouldDirty: true })}
              />
            ))}
          </div>
        </fieldset>
        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="mb-2 font-semibold text-ink">Engine settings (empty = default)</legend>
          <TextInput label="Question budget" type="number" error={errors.config?.question_budget} {...form.register("config.question_budget", num)} />
          <TextInput label="Minimum questions" type="number" error={errors.config?.min_questions} {...form.register("config.min_questions", num)} />
          <TextInput label="Stop at probability" type="number" step="0.05" error={errors.config?.stop_probability} {...form.register("config.stop_probability", num)} />
          <TextInput label="Stop margin" type="number" step="0.05" error={errors.config?.stop_margin} {...form.register("config.stop_margin", num)} />
        </fieldset>
        <ErrorLine error={error} />
        <Button type="submit" size="cta">
          Save in draft
        </Button>
      </form>
    </Dialog>
  );
}

function FilterDialog({ filter, onClose, onSaved }: { filter: Filter | null; onClose: () => void; onSaved: () => void }) {
  const { save, error } = useSave(onSaved, onClose);
  type F = z.infer<typeof filterSchema>;
  const form = useForm<F>({
    resolver: zodResolver(filterSchema),
    defaultValues: { name: filter?.name ?? "", fuel: (filter?.fuel ?? []) as F["fuel"], transmission: (filter?.transmission ?? []) as F["transmission"] },
  });
  const errors = form.formState.errors;
  const submit = form.handleSubmit(({ name, ...v }) => save("vehicle_filter", name, v));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={filter ? `Edit filter ${filter.name}` : "New vehicle filter"}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {!filter && <TextInput label="Name" error={errors.name} {...form.register("name")} />}
        <fieldset className="flex flex-wrap gap-x-4">
          <legend className="font-semibold text-ink">Fuels</legend>
          {FUELS.map((f) => (
            <Checkbox key={f} label={f} value={f} {...form.register("fuel")} />
          ))}
        </fieldset>
        <fieldset className="flex flex-wrap gap-x-4">
          <legend className="font-semibold text-ink">Gearboxes</legend>
          {TRANSMISSIONS.map((t) => (
            <Checkbox key={t} label={t} value={t} {...form.register("transmission")} />
          ))}
        </fieldset>
        {errors.fuel?.message && <p className="text-sm font-semibold text-orange-text">{errors.fuel.message}</p>}
        <ErrorLine error={error} />
        <Button type="submit" size="cta">
          Save in draft
        </Button>
      </form>
    </Dialog>
  );
}
