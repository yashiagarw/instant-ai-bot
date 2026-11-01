"use client";

import { useCallback, useState, type FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@im/ui/button";
import { ErrorBox } from "@/components/error-box";
import { Field } from "@/components/field";
import { Select, TextArea } from "@/components/form";
import { adminApi, errorMessage, type OutcomeInput, type PartUsed, type RequestDetail } from "@/lib/api";
import { outcomeProblems } from "@/lib/ops";
import { useLoad } from "@/lib/use-load";

const numberOrNull = (v: string) => (v.trim() === "" ? null : Number(v));

/** Complete the job: the fault the mechanic confirmed (training data, compared with the AI's top 3), parts, final cost
 * and the mechanic's notes. Only for a job in progress. */
export function CompleteJob({ request, onDone }: { request: RequestDetail; onDone: (r: RequestDetail) => void }) {
  const { state, reload } = useLoad(useCallback((s: AbortSignal) => adminApi.faultOptions(request.id, s), [request.id]));
  const [fault, setFault] = useState("");
  const [otherText, setOtherText] = useState("");
  const [parts, setParts] = useState<{ name: string; quantity: string; price: string }[]>([]);
  const [cost, setCost] = useState("");
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body: OutcomeInput = {
      confirmed_fault_key: fault,
      other_text: fault === "other" ? otherText.trim() : "",
      parts_used: parts.map<PartUsed>((p) => ({ name: p.name.trim(), quantity: Number(p.quantity), price_inr: numberOrNull(p.price) })),
      final_cost_inr: numberOrNull(cost),
      mechanic_notes: notes.trim(),
    };
    const problems = outcomeProblems(body);
    setErrors(problems);
    if (Object.keys(problems).length) return;
    setBusy(true);
    setError("");
    try {
      onDone(await adminApi.completeJob(request.id, body));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const options = state.kind === "ready" ? state.data : [];
  return (
    <form onSubmit={submit} noValidate aria-labelledby="complete-h" className="flex flex-col gap-4 rounded-3xl border-2 border-cta bg-white p-4 sm:p-6">
      <div className="flex flex-col gap-1">
        <h2 id="complete-h" className="text-xl font-black text-ink">
          Complete the job
        </h2>
        <p className="text-sm text-ink/80">
          Record what the mechanic actually found. It is compared with the AI&apos;s top causes and kept for training.
        </p>
      </div>
      {state.kind === "error" && <ErrorBox message={state.message} onRetry={reload} />}
      <Select
        label="Confirmed fault"
        value={fault}
        onChange={(e) => setFault(e.target.value)}
        error={errors.confirmed_fault_key ? { message: errors.confirmed_fault_key } : undefined}
        options={[
          { value: "", label: state.kind === "loading" ? "Loading the faults…" : "Choose the fault" },
          ...options.map((o) => ({ value: o.fault_key, label: `${o.ai_rank ? `AI #${o.ai_rank}: ` : ""}${o.name} (${o.fault_key})` })),
          { value: "other", label: "Other (describe it)" },
        ]}
      />
      {fault === "other" && (
        <TextArea
          label="What was the fault?"
          rows={2}
          value={otherText}
          onChange={(e) => setOtherText(e.target.value)}
          maxLength={500}
          error={errors.other_text ? { message: errors.other_text } : undefined}
        />
      )}
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 font-semibold text-ink">Parts used</legend>
        {parts.length === 0 && <p className="text-sm text-ink/75">None</p>}
        {parts.map((p, i) => (
          <div key={i} className="flex flex-col gap-1 rounded-2xl bg-warm-white p-3">
            <div className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end">
              <Field label={`Part ${i + 1}`} value={p.name} maxLength={120} onChange={(e) => setParts(parts.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
              <Field label={`Part ${i + 1} quantity`} type="number" min={1} value={p.quantity} onChange={(e) => setParts(parts.map((x, j) => (j === i ? { ...x, quantity: e.target.value } : x)))} />
              <Field label={`Part ${i + 1} price (₹)`} type="number" min={0} value={p.price} onChange={(e) => setParts(parts.map((x, j) => (j === i ? { ...x, price: e.target.value } : x)))} />
              <button
                type="button"
                aria-label={`Remove part ${i + 1}`}
                onClick={() => setParts(parts.filter((_, j) => j !== i))}
                className="inline-flex min-h-12 items-center justify-center rounded-full px-3 text-ink outline-none hover:bg-white focus-visible:ring-3 focus-visible:ring-ring"
              >
                <Trash2 aria-hidden="true" className="size-4" />
              </button>
            </div>
            {errors[`part-${i}`] && <p className="text-sm font-semibold text-orange-text">{errors[`part-${i}`]}</p>}
          </div>
        ))}
        <button
          type="button"
          onClick={() => setParts([...parts, { name: "", quantity: "1", price: "" }])}
          className="inline-flex min-h-11 items-center gap-1 self-start rounded-full border border-border px-4 font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
        >
          <Plus aria-hidden="true" className="size-4" /> Add a part
        </button>
      </fieldset>
      <Field label="Final cost (₹)" type="number" min={0} value={cost} onChange={(e) => setCost(e.target.value)} error={errors.final_cost_inr} />
      <TextArea label="Mechanic's notes" value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} />
      {Object.keys(errors).length > 0 && (
        <p role="alert" className="font-semibold text-orange-text">
          Please fix the highlighted fields.
        </p>
      )}
      {error && <ErrorBox message={error} />}
      <Button type="submit" disabled={busy} className="h-12 self-start rounded-full px-6 text-lg font-bold">
        Complete job
      </Button>
    </form>
  );
}
