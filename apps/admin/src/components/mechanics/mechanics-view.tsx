"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Plus } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { Checkbox, TextArea, TextInput } from "@/components/form";
import { MapView } from "@/components/map-view";
import { useMe } from "@/components/staff-shell";
import { adminApi, type CategoryOption, errorMessage, type Mechanic } from "@/lib/api";
import { precisionNote, WEEKDAYS } from "@/lib/ops";
import { type MechanicForm, mechanicSchema } from "@/lib/schemas";
import { useLoad } from "@/lib/use-load";

export const BLANK_MECHANIC: MechanicForm = {
  name: "",
  phone: "",
  base_pincode: "",
  base_area: "",
  rating: null,
  max_jobs_per_day: 4,
  active: true,
  notes: "",
};

/** Category names for skill codes (the public category list; codes when it can't be loaded). */
export function useCategories() {
  const { state } = useLoad(useCallback((s: AbortSignal) => adminApi.categories(s), []));
  const list = useMemo<CategoryOption[]>(() => (state.kind === "ready" ? state.data : []), [state]);
  const name = useCallback((code: string) => list.find((c) => c.code === code)?.name ?? code, [list]);
  return { list, name, failed: state.kind === "error" };
}

export function shiftsSummary(m: Mechanic): string {
  if (!m.shifts.length) return "Any time on duty";
  const days = [...new Set(m.shifts.map((s) => s.weekday))].sort();
  return `${m.shifts.length} shift${m.shifts.length === 1 ? "" : "s"} · ${days.map((d) => WEEKDAYS[d].slice(0, 3)).join(" ")}`;
}

/** On / off duty, as a switch (mechanics.manage) or as text. */
export function DutySwitch({ mechanic, onChange }: { mechanic: Mechanic; onChange?: (m: Mechanic) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const on = mechanic.on_duty;
  if (!onChange) return <span className={cn("font-bold", on ? "text-success" : "text-ink/75")}>{on ? "On duty" : "Off duty"}</span>;
  return (
    <span className="flex flex-col gap-1">
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={`On duty: ${mechanic.name}`}
        disabled={busy || (!on && !mechanic.active)}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            onChange(await adminApi.setDuty(mechanic.id, !on));
          } catch (e) {
            setError(errorMessage(e));
          } finally {
            setBusy(false);
          }
        }}
        className={cn(
          "inline-flex min-h-11 items-center gap-2 self-start rounded-full border-2 px-3 font-bold whitespace-nowrap outline-none focus-visible:ring-3 focus-visible:ring-ring disabled:opacity-60",
          on ? "border-success bg-success-bg text-success" : "border-border bg-white text-ink/80",
        )}
      >
        <span aria-hidden="true" className={cn("size-3 rounded-full", on ? "bg-success" : "bg-ink/40")} />
        {on ? "On duty" : "Off duty"}
      </button>
      {error && (
        <span role="alert" className="text-sm font-semibold text-orange-text">
          {error}
        </span>
      )}
    </span>
  );
}

export function MechanicFields({ form }: { form: ReturnType<typeof useForm<MechanicForm>> }) {
  const e = form.formState.errors;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <TextInput label="Name" hint="Customers see the first word only." autoComplete="off" error={e.name} {...form.register("name")} />
      <TextInput label="Mobile number" type="tel" inputMode="tel" autoComplete="off" error={e.phone} {...form.register("phone")} />
      <TextInput label="Base pincode" inputMode="numeric" maxLength={6} error={e.base_pincode} {...form.register("base_pincode")} />
      <TextInput label="Base area (e.g. Malviya Nagar)" error={e.base_area} {...form.register("base_area")} />
      <TextInput
        label="Rating (0 to 5, optional)"
        type="number"
        step="0.1"
        error={e.rating}
        {...form.register("rating", { setValueAs: (v) => (v === "" || v === null ? null : Number(v)) })}
      />
      <TextInput label="Most jobs a day" type="number" error={e.max_jobs_per_day} {...form.register("max_jobs_per_day", { valueAsNumber: true })} />
      <TextArea label="Notes (internal)" error={e.notes} className="md:col-span-2" {...form.register("notes")} />
      <Checkbox label="Active (inactive mechanics are never suggested)" {...form.register("active")} />
    </div>
  );
}

export function MechanicsView() {
  const { me } = useMe();
  const manage = me.permissions.includes("mechanics.manage");
  const [inactive, setInactive] = useState(false);
  const { state, reload, set } = useLoad(useCallback((s: AbortSignal) => adminApi.mechanics(inactive, s), [inactive]));
  const categories = useCategories();
  const [adding, setAdding] = useState(false);

  const replace = useCallback(
    (m: Mechanic) => state.kind === "ready" && set(state.data.map((x) => (x.id === m.id ? m : x))),
    [state, set],
  );

  const columns = useMemo<ColumnDef<Mechanic, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Name",
        cell: ({ row }) => (
          <span className="flex flex-col gap-0.5">
            <Link href={`/mechanics/${row.original.id}`} className="font-bold text-orange-text underline underline-offset-4">
              {row.original.name}
            </Link>
            {row.original.dev_seed && <span className="text-xs font-bold text-amber-text">Fake (development seed)</span>}
            {!row.original.active && <span className="text-xs font-bold text-ink/75">Inactive</span>}
          </span>
        ),
      },
      {
        id: "duty",
        accessorFn: (m) => (m.on_duty ? "On duty" : "Off duty"),
        header: "Duty",
        cell: ({ row }) => <DutySwitch mechanic={row.original} onChange={manage ? replace : undefined} />,
      },
      {
        id: "base",
        accessorFn: (m) => `${m.base_area} ${m.base_pincode}`,
        header: "Base",
        cell: ({ row }) => {
          const m = row.original;
          const note = precisionNote(m.base_precision);
          return (
            <span className="flex flex-col">
              <span>{m.base_area || "–"}</span>
              <span className="text-sm text-ink/75">
                {m.base_pincode}
                {note && <span className="ml-1 font-semibold text-amber-text">({note})</span>}
              </span>
            </span>
          );
        },
      },
      {
        id: "skills",
        accessorFn: (m) => m.skills.map(categories.name),
        header: "Skills",
        enableSorting: false,
        cell: ({ row }) => (row.original.skills.length ? row.original.skills.map(categories.name).join(", ") : "None yet"),
      },
      { id: "zones", accessorFn: (m) => m.zones.length, header: "Zones" },
      { id: "shifts", accessorFn: shiftsSummary, header: "Shifts" },
      { id: "rating", accessorFn: (m) => m.rating ?? -1, header: "Rating", cell: ({ row }) => row.original.rating ?? "Not rated" },
      { id: "today", accessorFn: (m) => m.jobs_today, header: "Jobs today", cell: ({ row }) => `${row.original.jobs_today} of ${row.original.max_jobs_per_day}` },
      {
        id: "acceptance",
        accessorFn: (m) => m.acceptance_rate ?? -1,
        header: "Accepts",
        cell: ({ row }) => (row.original.acceptance_rate === null ? "No offers yet" : `${Math.round(row.original.acceptance_rate * 100)}%`),
      },
    ],
    [categories.name, manage, replace],
  );

  if (state.kind === "loading") return <p role="status">Loading mechanics…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const mapped = state.data.filter((m) => m.base_point);

  return (
    <div className="flex flex-col gap-4">
      <MapView
        label="Where the mechanics are based"
        points={mapped.map((m) => ({
          id: String(m.id),
          lat: m.base_point![0],
          lon: m.base_point![1],
          label: `${m.name} (${m.on_duty ? "on duty" : "off duty"})`,
          tone: "mechanic",
          rough: m.base_precision !== "pincode",
        }))}
      />
      <Checkbox label="Show inactive mechanics" checked={inactive} onChange={(e) => setInactive(e.target.checked)} />
      <DataTable
        data={state.data}
        columns={columns}
        caption="Mechanics"
        searchLabel="Search mechanics (name, area, pincode, skill)"
        filters={[{ column: "duty", label: "Duty" }]}
        getRowId={(m) => String(m.id)}
        empty="No mechanics yet."
        actions={
          manage && (
            <Button type="button" className="h-11 rounded-full px-5 text-base font-bold" onClick={() => setAdding(true)}>
              <Plus aria-hidden="true" className="size-5" /> Add mechanic
            </Button>
          )
        }
        csv={{
          filename: "mechanics",
          columns: [
            { header: "Name", value: (m) => m.name },
            { header: "Duty", value: (m) => (m.on_duty ? "on" : "off") },
            { header: "Base pincode", value: (m) => m.base_pincode },
            { header: "Base area", value: (m) => m.base_area },
            { header: "Skills", value: (m) => m.skills },
            { header: "Rating", value: (m) => String(m.rating ?? "") },
            { header: "Jobs today", value: (m) => String(m.jobs_today) },
          ],
        }}
      />
      {adding && <AddMechanic onClose={() => setAdding(false)} />}
    </div>
  );
}

function AddMechanic({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const form = useForm<MechanicForm>({ resolver: zodResolver(mechanicSchema), defaultValues: BLANK_MECHANIC });
  const submit = form.handleSubmit(async (v) => {
    setError("");
    try {
      const m = await adminApi.saveMechanic(null, v);
      router.push(`/mechanics/${m.id}?added=1`);
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title="Add mechanic" description="They work their base pincode until you set their zones.">
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <MechanicFields form={form} />
        {error && <ErrorBox message={error} />}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={form.formState.isSubmitting} className="h-12 rounded-full px-6 text-lg font-bold">
            Save mechanic
          </Button>
          <Button type="button" variant="outline" className="h-12 rounded-full px-5 text-base" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
