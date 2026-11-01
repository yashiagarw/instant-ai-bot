"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { Plus } from "lucide-react";

import { Button } from "@im/ui/button";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { EditedBadge, Select, TextArea, TextInput } from "@/components/form";
import { useDraft, useDraftData } from "@/components/knowledge/draft";
import { adminApi, errorMessage, type FaultRow } from "@/lib/api";
import { newFaultSchema } from "@/lib/schemas";

const fetchAll = (v: number, signal: AbortSignal) =>
  Promise.all([adminApi.faults(v, undefined, signal), adminApi.taxonomy(v, signal)]).then(([faults, tax]) => ({ faults, tax }));

export function FaultsTab() {
  const { draft, writable } = useDraft();
  const { state, reload } = useDraftData(fetchAll);
  const [creating, setCreating] = useState(false);

  const columns = useMemo<ColumnDef<FaultRow, unknown>[]>(
    () => [
      {
        accessorKey: "key",
        header: "Fault",
        cell: ({ row }) => (
          <Link
            href={`/knowledge/faults/${encodeURIComponent(row.original.key)}?draft=${draft?.id}`}
            className="font-mono font-bold text-orange-text underline underline-offset-4"
          >
            {row.original.key}
          </Link>
        ),
      },
      {
        accessorKey: "name",
        header: "Name",
        cell: ({ row }) => (
          <span className="flex flex-wrap items-center gap-2">
            {row.original.name}
            <EditedBadge show={row.original.edited} label={row.original.new ? "New in this draft" : "Edited"} />
          </span>
        ),
      },
      { accessorKey: "category", header: "Category" },
      { id: "symptoms", accessorFn: (f) => f.lines.symptom ?? 0, header: "Symptoms" },
      { id: "steps", accessorFn: (f) => f.lines.diagnosis_step ?? 0, header: "Diagnostic steps" },
      { id: "repairs", accessorFn: (f) => f.lines.resolution_step ?? 0, header: "Repair steps" },
      { id: "edited", accessorFn: (f) => (f.edited ? "edited" : "unchanged"), header: "In this draft" },
    ],
    [draft?.id],
  );

  if (state.kind === "loading") return <p role="status">Loading faults…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const { faults, tax } = state.data;
  const categories = tax.categories.map((c) => ({ value: c.code, label: c.name }));

  return (
    <>
      <DataTable
        data={faults}
        columns={columns}
        caption="Faults"
        searchLabel="Search faults (key, name, category)"
        filters={[
          { column: "category", label: "Category", options: categories },
          { column: "edited", label: "In this draft", options: [{ value: "edited", label: "Edited" }, { value: "unchanged", label: "Unchanged" }] },
        ]}
        pageSize={25}
        getRowId={(f) => f.key}
        actions={
          writable && (
            <Button type="button" className="h-11 rounded-full px-5 text-base font-bold" onClick={() => setCreating(true)}>
              <Plus aria-hidden="true" className="size-5" /> New fault
            </Button>
          )
        }
        csv={{
          filename: `faults-v${draft?.id}`,
          columns: [
            { header: "Fault", value: (f) => f.key },
            { header: "Name", value: (f) => f.name },
            { header: "Category", value: (f) => f.category },
            { header: "Symptoms", value: (f) => String(f.lines.symptom ?? 0) },
            { header: "Edited", value: (f) => (f.edited ? "yes" : "") },
          ],
        }}
      />
      {draft && <NewFault open={creating} onOpenChange={setCreating} version={draft.id} categories={categories} onCreated={reload} />}
    </>
  );
}

function NewFault({
  open,
  onOpenChange,
  version,
  categories,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  version: number;
  categories: { value: string; label: string }[];
  onCreated: () => void;
}) {
  const router = useRouter();
  const { touched } = useDraft();
  const [error, setError] = useState("");
  const form = useForm<z.infer<typeof newFaultSchema>>({ resolver: zodResolver(newFaultSchema), defaultValues: { name: "", category_code: "", description: "" } });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    setError("");
    const data = {
      name: values.name,
      description: values.description,
      category_code: values.category_code,
      likely_fault: "",
      road_repairable: "unknown",
      road_repairable_text: "",
      repair_location: "",
      towing_conditions_text: "",
      repair_time_text: "",
      severity: null,
      safety_critical: false,
      requires: [],
      prior: null,
    };
    try {
      const r = await adminApi.saveEdit(version, "fault", "", data, "new fault");
      touched();
      onCreated();
      router.push(`/knowledge/faults/${encodeURIComponent(r.key)}?draft=${version}`);
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="New fault">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <TextInput label="Name" error={errors.name} {...form.register("name")} />
        <Select label="Category" error={errors.category_code} options={[{ value: "", label: "Choose a category" }, ...categories]} {...form.register("category_code")} />
        <TextArea label="Description" error={errors.description} {...form.register("description")} />
        <p className="text-sm text-ink/75">It gets the next key of the category&apos;s file. Add its lines, phrases and safety rules next.</p>
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <Button type="submit" size="cta" disabled={form.formState.isSubmitting}>
          Create fault
        </Button>
      </form>
    </Dialog>
  );
}
