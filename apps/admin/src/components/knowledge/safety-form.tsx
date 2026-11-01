"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { ShieldAlert, Trash2 } from "lucide-react";

import { Button } from "@im/ui/button";
import { Dialog } from "@im/ui/dialog";
import { Checkbox, Select, TextArea, TextInput } from "@/components/form";
import { useDraft } from "@/components/knowledge/draft";
import { adminApi, errorMessage, type SafetyData, type SafetyRuleRow } from "@/lib/api";
import { type SafetyForm, safetySchema } from "@/lib/schemas";

export const SAFETY_STATUS: Record<SafetyData["status"], string> = {
  draft: "Draft (not used)",
  active_pending_signoff: "Live, waiting for sign-off",
  approved: "Live, signed off",
  rejected: "Rejected (not used)",
};

/** Edit one safety rule. Always warned: these rules decide when customers are told to stop driving. Danger red is
 * kept for safety, so this warning uses it. */
export function SafetyRuleDialog({
  rule,
  open,
  onOpenChange,
  onSaved,
}: {
  rule: SafetyRuleRow;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSaved: () => void;
}) {
  const { draft, touched } = useDraft();
  const [error, setError] = useState("");
  const form = useForm<SafetyForm>({
    resolver: zodResolver(safetySchema),
    defaultValues: {
      risk_level: rule.risk_level,
      stop_driving_trigger: rule.stop_driving_trigger,
      roadside_action: rule.roadside_action,
      towing_recommendation: rule.towing_recommendation,
      status: rule.status,
      trigger_phrases: rule.trigger_phrases.map((text) => ({ text })),
      understood: false as unknown as true,
    },
  });
  const phrases = useFieldArray({ control: form.control, name: "trigger_phrases" });
  const errors = form.formState.errors;
  const global = rule.scope === "global";

  const submit = form.handleSubmit(async (v) => {
    if (!draft) return;
    setError("");
    const approved = v.status === "approved";
    const data: SafetyData = {
      risk_level: v.risk_level,
      stop_driving_trigger: v.stop_driving_trigger,
      roadside_action: v.roadside_action,
      towing_recommendation: v.towing_recommendation,
      status: v.status,
      // Approving here means signing off under your name (the server records who and when).
      signed_off_by: approved ? (rule.signed_off_by ?? null) : rule.signed_off_by,
      signed_off_at: approved ? (rule.signed_off_at ?? null) : rule.signed_off_at,
      trigger_phrases: v.trigger_phrases.map((p) => p.text),
    };
    try {
      if (approved && !rule.signed_off_by) {
        await adminApi.saveEdit(draft.id, "safety_rule", rule.key, { ...data, status: rule.status });
        await adminApi.signOff(draft.id, "safety_rule", rule.key);
      } else {
        await adminApi.saveEdit(draft.id, "safety_rule", rule.key, data);
      }
      touched();
      onSaved();
      onOpenChange(false);
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={`Safety rule: ${global ? "emergency" : rule.fault_key ?? rule.key}`} className="max-w-2xl">
      <div role="note" className="flex items-start gap-3 rounded-2xl border-2 border-danger bg-white p-3 text-ink" data-testid="safety-warning">
        <ShieldAlert aria-hidden="true" className="mt-0.5 size-6 shrink-0 text-danger" />
        <p>
          <strong>You are changing a safety rule.</strong> These rules decide when customers are told to stop driving or call for help.
          The old and new values are written to the audit log, and the change is listed by name on the publish page.
        </p>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Risk level" error={errors.risk_level} options={["high", "medium", "low"].map((r) => ({ value: r, label: r }))} {...form.register("risk_level")} />
          <Select
            label="Status"
            error={errors.status}
            options={Object.entries(SAFETY_STATUS).map(([value, label]) => ({ value, label }))}
            hint="Rejected rules stop being used; rules are never deleted."
            {...form.register("status")}
          />
        </div>
        <TextArea label="When to stop driving" error={errors.stop_driving_trigger} {...form.register("stop_driving_trigger")} />
        <TextArea label="What to do at the roadside" error={errors.roadside_action} {...form.register("roadside_action")} />
        <TextArea label="Towing" error={errors.towing_recommendation} {...form.register("towing_recommendation")} />
        <fieldset className="flex flex-col gap-2">
          <legend className="font-semibold text-ink">Trigger phrases (customer words that fire it; any language)</legend>
          {phrases.fields.map((f, i) => (
            <div key={f.id} className="flex items-end gap-2">
              <TextInput className="flex-1" label={`Phrase ${i + 1}`} error={errors.trigger_phrases?.[i]?.text} {...form.register(`trigger_phrases.${i}.text`)} />
              <button type="button" aria-label={`Remove phrase ${i + 1}`} onClick={() => phrases.remove(i)} className="flex size-12 items-center justify-center rounded-full hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring focus-visible:outline-none">
                <Trash2 aria-hidden="true" className="size-5" />
              </button>
            </div>
          ))}
          <Button type="button" variant="outline" className="h-11 self-start rounded-full px-5 text-base" onClick={() => phrases.append({ text: "" })}>
            Add a phrase
          </Button>
        </fieldset>
        <Checkbox label="I checked this safety change" {...form.register("understood")} />
        {errors.understood && <p className="text-sm font-semibold text-orange-text">{errors.understood.message}</p>}
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <Button type="submit" size="cta" disabled={form.formState.isSubmitting}>
          Save safety rule in draft
        </Button>
      </form>
    </Dialog>
  );
}
