"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { TriangleAlert } from "lucide-react";

import { Button } from "@im/ui/button";
import { Dialog } from "@im/ui/dialog";
import { Checkbox, numberOrNull, Select, TextInput } from "@/components/form";
import { useDraft } from "@/components/knowledge/draft";
import { adminApi, errorMessage, type PriceRow } from "@/lib/api";
import { fromTriState, type PriceForm, priceSchema, SECOND_LOOK_INR, SEGMENTS, triState } from "@/lib/schemas";

const TRI = [
  { value: "unknown", label: "Not stated" },
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

/** Add or change one price of a part. A source (supplier or link) and the check date are required; 20,000 rupees or
 * more is flagged until a second person checks it. */
export function PriceDialog({ partKey, row, onClose, onSaved }: { partKey: string; row: PriceRow | null; onClose: () => void; onSaved: (warning: string | null) => void }) {
  const { draft, touched } = useDraft();
  const [error, setError] = useState("");
  const form = useForm<PriceForm>({
    resolver: zodResolver(priceSchema),
    defaultValues: {
      segment: (row?.segment as PriceForm["segment"]) ?? "budget",
      price_inr: row?.price_inr ?? (undefined as unknown as number),
      price_max_inr: row?.price_max_inr ?? null,
      supplier: row?.supplier ?? "",
      source_url: row?.source_url ?? "",
      checked_on: row?.checked_on ?? new Date().toISOString().slice(0, 10),
      verification_status: (row?.verification_status as PriceForm["verification_status"]) ?? "approx",
      gst_included: triState(row?.gst_included ?? null),
      fitting_included: triState(row?.fitting_included ?? null),
      model_verified: row?.model_verified ?? false,
      price_basis: row?.price_basis ?? "",
      note: row?.note ?? "",
    },
  });
  const e = form.formState.errors;
  const [lo, hi] = useWatch({ control: form.control, name: ["price_inr", "price_max_inr"] });
  const big = Math.max(Number(lo) || 0, Number(hi) || 0) >= SECOND_LOOK_INR;

  const submit = form.handleSubmit(async (v) => {
    setError("");
    const { segment, ...rest } = v;
    const data = {
      ...rest,
      gst_included: fromTriState(v.gst_included),
      fitting_included: fromTriState(v.fitting_included),
      second_look_by: row?.second_look_by ?? null,
      second_look_at: row?.second_look_at ?? null,
    };
    try {
      const r = await adminApi.saveEdit(draft!.id, "part_price", row ? row.key : `${partKey}|${segment}|`, data);
      touched();
      onSaved(r.warning);
    } catch (err) {
      setError(errorMessage(err));
    }
  });

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={row ? "Edit price" : "Add a price"} className="max-w-2xl">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-3">
          <Select label="Segment" disabled={!!row} options={SEGMENTS.map((x) => ({ value: x, label: x }))} {...form.register("segment")} />
          <TextInput label="Price (₹)" type="number" inputMode="numeric" error={e.price_inr} {...form.register("price_inr", { valueAsNumber: true })} />
          <TextInput label="Up to (₹, a range)" type="number" inputMode="numeric" error={e.price_max_inr} {...form.register("price_max_inr", { setValueAs: numberOrNull })} />
        </div>
        {big && (
          <p role="note" className="flex items-start gap-2 rounded-2xl bg-amber-bg p-3 text-amber-text" data-testid="big-price">
            <TriangleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
            ₹{SECOND_LOOK_INR.toLocaleString("en-IN")} or more: flagged until a second person checks it.
          </p>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="Source: supplier" error={e.supplier} hint="The supplier or a link is required." {...form.register("supplier")} />
          <TextInput label="Source: link" type="url" error={e.source_url} {...form.register("source_url")} />
          <TextInput label="Checked on" type="date" error={e.checked_on} {...form.register("checked_on")} />
          <Select
            label="Verification"
            options={[
              { value: "checked", label: "checked on the site" },
              { value: "listed_recheck", label: "listed, recheck" },
              { value: "approx", label: "approx" },
            ]}
            {...form.register("verification_status")}
          />
          <Select label="GST included" options={TRI} {...form.register("gst_included")} />
          <Select label="Fitting included" options={TRI} {...form.register("fitting_included")} />
          <TextInput label="Price basis (per piece, per litre ...)" error={e.price_basis} {...form.register("price_basis")} />
          <TextInput label="Note" error={e.note} {...form.register("note")} />
        </div>
        <Checkbox label="Checked for this exact car model (model-verified)" {...form.register("model_verified")} />
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" size="cta" disabled={form.formState.isSubmitting}>
            Save price in draft
          </Button>
          {row && (
            <Button
              type="button"
              variant="outline"
              className="h-12 rounded-full px-6 text-base"
              onClick={() =>
                adminApi
                  .saveEdit(draft!.id, "part_price", row.key, null, "deleted in the editor")
                  .then(() => {
                    touched();
                    onSaved(null);
                  })
                  .catch((err) => setError(errorMessage(err)))
              }
            >
              Delete price
            </Button>
          )}
        </div>
      </form>
    </Dialog>
  );
}
