"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { Trash2 } from "lucide-react";

import { Button } from "@im/ui/button";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { SaveStatus, Select, TextInput, useStatus } from "@/components/form";
import { DraftProvider, useDraft, useDraftData } from "@/components/knowledge/draft";
import { adminApi, errorMessage, type GeneratedQuestion } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { type GeneratedForm, generatedSchema } from "@/lib/schemas";

/** Review queues: questions the LLM proposed (approve after editing, or reject) and questions checked automatically
 * that wait for a person's sign-off. With no LLM API the first is usually empty. */
export function ReviewView() {
  return (
    <DraftProvider>
      <Queues />
    </DraftProvider>
  );
}

function Queues() {
  const { draft } = useDraft();
  if (!draft || draft.building) return null;
  return (
    <div className="flex flex-col gap-6">
      <Generated />
      <PendingQuestions />
    </div>
  );
}

function Generated() {
  const { writable } = useDraft();
  const [items, setItems] = useState<GeneratedQuestion[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [approving, setApproving] = useState<GeneratedQuestion | null>(null);
  const [status, setStatus] = useStatus();
  useEffect(() => {
    const ctrl = new AbortController();
    adminApi
      .generatedQuestions("generated", ctrl.signal)
      .then(setItems)
      .catch((e) => !ctrl.signal.aborted && setError(errorMessage(e)));
    return () => ctrl.abort();
  }, [attempt]);
  const reload = () => setAttempt((a) => a + 1);

  return (
    <section aria-labelledby="generated-heading" className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:p-5">
      <h2 id="generated-heading" className="text-2xl font-black text-ink">
        Questions proposed by the LLM
      </h2>
      <p className="text-ink/80">
        Proposed during diagnoses when no approved question fitted (only with an LLM provider switched on). Approving adds the question to the draft
        with a &quot;Not sure&quot; answer; give its answers effects in the question editor.
      </p>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!items && !error && <p role="status">Loading…</p>}
      {items && items.length === 0 && <p className="text-ink/70">Nothing waiting. (No LLM API is configured, so none are proposed.)</p>}
      <ul className="flex flex-col gap-3">
        {items?.map((g) => (
          <li key={g.id} className="flex flex-col gap-2 rounded-2xl border border-border p-3">
            <p className="font-bold text-ink">{g.text}</p>
            <p className="text-sm text-ink/75">
              {g.category_code ?? "no category"} · {g.options.join(" / ")} · {dateTime(g.created_at)}
              {g.reason && <> · why: {g.reason}</>}
            </p>
            {writable && (
              <span className="flex flex-wrap gap-2">
                <Button type="button" className="h-11 rounded-full px-4 text-base font-bold" onClick={() => setApproving(g)}>
                  Edit and approve
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="h-11 rounded-full px-4 text-base"
                  onClick={() =>
                    adminApi
                      .rejectGenerated(g.id)
                      .then(() => {
                        setStatus({ kind: "saved", text: "Rejected." });
                        reload();
                      })
                      .catch((e) => setStatus({ kind: "error", text: errorMessage(e) }))
                  }
                >
                  Reject
                </Button>
              </span>
            )}
          </li>
        ))}
      </ul>
      <SaveStatus status={status} />
      {approving && (
        <ApproveDialog
          question={approving}
          onClose={() => setApproving(null)}
          onDone={() => {
            setStatus({ kind: "saved", text: "Approved: added to the draft." });
            reload();
          }}
        />
      )}
    </section>
  );
}

function ApproveDialog({ question, onClose, onDone }: { question: GeneratedQuestion; onClose: () => void; onDone: () => void }) {
  const { draft, touched } = useDraft();
  const [error, setError] = useState("");
  const tax = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.taxonomy(v, s), []));
  const form = useForm<GeneratedForm>({
    resolver: zodResolver(generatedSchema),
    defaultValues: { category: question.category_code ?? "", stage: 3, text: question.text, options: question.options.map((label) => ({ label })) },
  });
  const options = useFieldArray({ control: form.control, name: "options" });
  const errors = form.formState.errors;
  const cats = tax.state.kind === "ready" ? tax.state.data.categories : [];
  const submit = form.handleSubmit(async (v) => {
    setError("");
    try {
      await adminApi.approveGenerated(question.id, { version_id: draft!.id, category: v.category, stage: v.stage, text: v.text, options: v.options.map((o) => o.label) });
      touched();
      onDone();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title="Approve a proposed question" className="max-w-2xl">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Select label="Category" error={errors.category} options={[{ value: "", label: "Choose a category" }, ...cats.map((c) => ({ value: c.code, label: c.name }))]} {...form.register("category")} />
        <TextInput label="Question" error={errors.text} {...form.register("text")} />
        <TextInput label="Stage" type="number" error={errors.stage} {...form.register("stage", { valueAsNumber: true })} />
        <fieldset className="flex flex-col gap-2">
          <legend className="font-semibold text-ink">Answers (Not sure is added)</legend>
          {errors.options?.message && <p className="text-sm font-semibold text-orange-text">{errors.options.message}</p>}
          {options.fields.map((o, i) => (
            <div key={o.id} className="flex items-end gap-2">
              <TextInput className="flex-1" label={`Answer ${i + 1}`} error={errors.options?.[i]?.label} {...form.register(`options.${i}.label`)} />
              <button type="button" aria-label={`Remove answer ${i + 1}`} onClick={() => options.remove(i)} className="flex size-12 items-center justify-center rounded-full hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring focus-visible:outline-none">
                <Trash2 aria-hidden="true" className="size-5" />
              </button>
            </div>
          ))}
          <Button type="button" variant="outline" className="h-11 self-start rounded-full px-5 text-base" onClick={() => options.append({ label: "" })}>
            Add an answer
          </Button>
        </fieldset>
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <Button type="submit" size="cta" disabled={form.formState.isSubmitting}>
          Approve into draft v{draft?.id}
        </Button>
      </form>
    </Dialog>
  );
}

function PendingQuestions() {
  const { draft, writable, touched } = useDraft();
  const { state, reload } = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.signoffQueue(v, s), []));
  const [status, setStatus] = useStatus();
  if (state.kind === "loading") return <p role="status">Loading questions waiting for sign-off…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const items = state.data.filter((i) => i.entity === "question" && i.pending);
  return (
    <section aria-labelledby="pending-heading" className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:p-5">
      <h2 id="pending-heading" className="text-2xl font-black text-ink">
        Questions waiting for sign-off ({items.length})
      </h2>
      <p className="text-ink/80">
        Approved automatically (claude_code, pending mechanic sign-off). Check each in the{" "}
        <Link href={`/knowledge?tab=questions&draft=${draft?.id}`} className="font-bold text-orange-text underline underline-offset-4">
          question editor
        </Link>{" "}
        and sign it off under your name.
      </p>
      <SaveStatus status={status} />
      <ul className="flex flex-col divide-y divide-border">
        {items.slice(0, 200).map((i) => (
          <li key={i.key} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="flex flex-col">
              <span className="font-semibold text-ink">{i.text}</span>
              <span className="text-sm text-ink/75">
                {i.category} · {i.key}
              </span>
            </span>
            {writable && (
              <Button
                type="button"
                variant="outline"
                className="h-11 rounded-full px-4 text-base"
                onClick={() =>
                  adminApi
                    .signOff(draft!.id, "question", i.key)
                    .then(() => {
                      setStatus({ kind: "saved", text: `Signed off: ${i.text}` });
                      touched();
                      reload();
                    })
                    .catch((e) => setStatus({ kind: "error", text: errorMessage(e) }))
                }
              >
                Sign off as me
              </Button>
            )}
          </li>
        ))}
      </ul>
      {items.length > 200 && <p className="text-sm text-ink/75">Showing 200 of {items.length}; use the Sign-off tab to filter.</p>}
    </section>
  );
}
