"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useState } from "react";
import { type Control, type FieldErrors, useFieldArray, useForm, type UseFormRegister } from "react-hook-form";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@im/ui/button";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { Checkbox, EditedBadge, SaveStatus, Select, TextInput, useStatus } from "@/components/form";
import { useDraft, useDraftData } from "@/components/knowledge/draft";
import { adminApi, errorMessage, type QuestionData, type QuestionRow } from "@/lib/api";
import { type QuestionForm, questionSchema } from "@/lib/schemas";

const STRENGTH_LABEL = { strong: "strong", moderate: "moderate", weak: "weak" } as const;

export function QuestionsTab() {
  const { draft, writable, touched } = useDraft();
  const [category, setCategory] = useState("");
  const taxonomy = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.taxonomy(v, s), []));
  const fetcher = useCallback((v: number, s: AbortSignal) => adminApi.questions(v, category, s), [category]);
  const { state, reload } = useDraftData(category ? fetcher : null);
  const [editing, setEditing] = useState<QuestionRow | "new" | null>(null);
  const [status, setStatus] = useStatus();

  const cats = taxonomy.state.kind === "ready" ? taxonomy.state.data.categories : [];
  return (
    <div className="flex flex-col gap-4">
      <label className="flex max-w-sm flex-col gap-1 font-semibold text-ink">
        Category
        <select className="h-12 rounded-xl border border-input bg-white px-4" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Choose a category</option>
          {cats.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      {category && state.kind === "loading" && <p role="status">Loading questions…</p>}
      {state.kind === "error" && <ErrorBox message={state.message} onRetry={reload} />}
      {category && state.kind === "ready" && (
        <>
          {writable && (
            <Button type="button" className="h-11 self-start rounded-full px-5 text-base font-bold" onClick={() => setEditing("new")}>
              <Plus aria-hidden="true" className="size-5" /> New question
            </Button>
          )}
          {state.data.questions.length === 0 && <p className="text-ink/70">No questions in this category yet.</p>}
          <ul className="flex flex-col gap-3" aria-label="Questions">
            {state.data.questions.map((q) => (
              <li key={q.key} className="flex flex-col gap-2 rounded-3xl border border-border bg-white p-4">
                <p className="flex flex-wrap items-center gap-2 font-bold text-ink">
                  {q.text} <EditedBadge show={q.edit} />
                  {q.status !== "approved" && <span className="text-sm text-ink/70">({q.status})</span>}
                </p>
                <p className="text-sm text-ink/75">
                  Stage {q.stage} · {q.key} · {q.reviewed_by ? `reviewed by ${q.reviewed_by}` : "not reviewed"}
                  {q.pending_signoff && " (pending sign-off)"}
                </p>
                <ul className="flex flex-col gap-1 text-sm text-ink">
                  {q.options.map((o) => (
                    <li key={o.label}>
                      <strong>{o.label}</strong>
                      {o.effects.length > 0 && ": " + o.effects.map((e) => `${e.effect === "supports" ? "+" : "−"}${e.fault} (${STRENGTH_LABEL[e.strength]})`).join(", ")}
                    </li>
                  ))}
                </ul>
                {writable && (
                  <span className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => setEditing(q)}>
                      Edit question
                    </Button>
                    {q.pending_signoff && (
                      <Button
                        type="button"
                        variant="outline"
                        className="h-11 rounded-full px-4 text-base"
                        onClick={() =>
                          adminApi
                            .signOff(draft!.id, "question", q.key)
                            .then(() => {
                              setStatus({ kind: "saved", text: "Signed off." });
                              touched();
                              reload();
                            })
                            .catch((e) => setStatus({ kind: "error", text: errorMessage(e) }))
                        }
                      >
                        Sign off as me
                      </Button>
                    )}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <SaveStatus status={status} />
          {editing && (
            <QuestionDialog
              question={editing === "new" ? null : editing}
              category={category}
              faults={state.data.faults}
              onClose={() => setEditing(null)}
              onSaved={() => {
                touched();
                reload();
              }}
            />
          )}
        </>
      )}
    </div>
  );
}

function QuestionDialog({
  question,
  category,
  faults,
  onClose,
  onSaved,
}: {
  question: QuestionRow | null;
  category: string;
  faults: { key: string; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { draft } = useDraft();
  const [error, setError] = useState("");
  const blank: QuestionForm = {
    stage: 3,
    text: "",
    status: "approved",
    options: [
      { label: "Yes", not_sure: false, effects: [] },
      { label: "No", not_sure: false, effects: [] },
      { label: "Not sure", not_sure: true, effects: [] },
    ],
  };
  const form = useForm<QuestionForm>({
    resolver: zodResolver(questionSchema),
    defaultValues: question ? { stage: question.stage, text: question.text, status: question.status, options: question.options } : blank,
  });
  const options = useFieldArray({ control: form.control, name: "options" });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (v) => {
    setError("");
    const data: QuestionData = { ...v, reviewed_by: question?.reviewed_by ?? null, reviewed_at: question?.reviewed_at ?? null };
    try {
      await adminApi.saveEdit(draft!.id, "question", question ? question.key : `${category}/`, data);
      onSaved();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  async function remove() {
    try {
      await adminApi.saveEdit(draft!.id, "question", question!.key, null, "deleted in the editor");
      onSaved();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={question ? "Edit question" : "New question"} className="max-w-3xl">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <TextInput label="Question" error={errors.text} {...form.register("text")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="Stage (2 = main complaint, 3+ = follow-up)" type="number" error={errors.stage} {...form.register("stage", { valueAsNumber: true })} />
          <Select label="Status" options={["approved", "draft", "rejected"].map((s) => ({ value: s, label: s }))} {...form.register("status")} />
        </div>
        <fieldset className="flex flex-col gap-3">
          <legend className="font-semibold text-ink">Answers and their effects (the weights the engine uses)</legend>
          {errors.options?.message && <p className="text-sm font-semibold text-orange-text">{errors.options.message}</p>}
          {errors.options?.root?.message && <p className="text-sm font-semibold text-orange-text">{errors.options.root.message}</p>}
          {options.fields.map((o, i) => (
            <div key={o.id} className="flex flex-col gap-2 rounded-2xl border border-border p-3">
              <div className="flex flex-wrap items-end gap-2">
                <TextInput className="min-w-48 flex-1" label={`Answer ${i + 1}`} error={errors.options?.[i]?.label} {...form.register(`options.${i}.label`)} />
                <Checkbox label="Not sure" {...form.register(`options.${i}.not_sure`)} />
                <button type="button" aria-label={`Remove answer ${i + 1}`} onClick={() => options.remove(i)} className="flex size-12 items-center justify-center rounded-full hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring focus-visible:outline-none">
                  <Trash2 aria-hidden="true" className="size-5" />
                </button>
              </div>
              <Effects index={i} control={form.control} register={form.register} errors={errors} faults={faults} />
            </div>
          ))}
          <Button type="button" variant="outline" className="h-11 self-start rounded-full px-5 text-base" onClick={() => options.insert(Math.max(options.fields.length - 1, 0), { label: "", not_sure: false, effects: [] })}>
            Add an answer
          </Button>
        </fieldset>
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" size="cta" disabled={form.formState.isSubmitting}>
            Save question in draft
          </Button>
          {question && (
            <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base" onClick={() => void remove()}>
              Delete question
            </Button>
          )}
        </div>
      </form>
    </Dialog>
  );
}

function Effects({
  index,
  control,
  register,
  errors,
  faults,
}: {
  index: number;
  control: Control<QuestionForm>;
  register: UseFormRegister<QuestionForm>;
  errors: FieldErrors<QuestionForm>;
  faults: { key: string; name: string }[];
}) {
  const effects = useFieldArray({ control, name: `options.${index}.effects` });
  return (
    <div className="flex flex-col gap-2 pl-2">
      {effects.fields.map((e, j) => (
        <div key={e.id} className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end">
          <Select
            label={`Effect ${j + 1}: fault`}
            error={errors.options?.[index]?.effects?.[j]?.fault}
            options={[{ value: "", label: "Choose a fault" }, ...faults.map((f) => ({ value: f.key, label: `${f.key} ${f.name}` }))]}
            {...register(`options.${index}.effects.${j}.fault`)}
          />
          <Select label="Effect" options={[{ value: "supports", label: "supports" }, { value: "rules_out", label: "rules out" }]} {...register(`options.${index}.effects.${j}.effect`)} />
          <Select label="Strength" options={["strong", "moderate", "weak"].map((s) => ({ value: s, label: s }))} {...register(`options.${index}.effects.${j}.strength`)} />
          <button type="button" aria-label={`Remove effect ${j + 1}`} onClick={() => effects.remove(j)} className="flex size-12 items-center justify-center rounded-full hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring focus-visible:outline-none">
            <Trash2 aria-hidden="true" className="size-5" />
          </button>
        </div>
      ))}
      <Button type="button" variant="outline" className="h-10 self-start rounded-full px-4 text-sm" onClick={() => effects.append({ fault: "", effect: "supports", strength: "moderate" })}>
        Add an effect
      </Button>
    </div>
  );
}
