"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState, type ReactNode } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import type { z } from "zod";
import { ArrowDown, ArrowLeft, ArrowUp, ImagePlus, Star, Trash2 } from "lucide-react";

import { Button } from "@im/ui/button";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { Checkbox, EditedBadge, numberOrNull, SaveStatus, Select, TextArea, TextInput, useStatus } from "@/components/form";
import { DraftProvider, useDraft, useDraftData } from "@/components/knowledge/draft";
import { SAFETY_STATUS, SafetyRuleDialog } from "@/components/knowledge/safety-form";
import { adminApi, errorMessage, type FaultDetail, mediaUrl, type SafetyRuleRow } from "@/lib/api";
import { type FaultForm, faultSchema, linesSchema, phraseSchema, REQUIREMENT_FIELDS, requiresFromForm, requiresToForm } from "@/lib/schemas";

const LINE_TYPES: { type: string; label: string; internal?: boolean }[] = [
  { type: "symptom", label: "Symptoms" },
  { type: "cause", label: "Causes" },
  { type: "diagnosis_step", label: "Diagnostic steps" },
  { type: "resolution_step", label: "Repair steps" },
  { type: "advice", label: "Advice for the customer" },
  { type: "safety", label: "Safety precautions" },
  { type: "towing_condition", label: "Towing conditions" },
  { type: "mechanic_task", label: "Mechanic task (internal, never shown to customers)", internal: true },
  { type: "mechanic_step", label: "Mechanic repair steps (internal, never shown to customers)", internal: true },
];

export function FaultEditorPage({ faultKey }: { faultKey: string }) {
  return (
    <DraftProvider>
      <FaultEditor faultKey={faultKey} />
    </DraftProvider>
  );
}

function Section({ title, id, children, badge }: { title: string; id: string; children: ReactNode; badge?: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-4 sm:p-5">
      <h2 id={id} className="flex flex-wrap items-center gap-2 text-xl font-black text-ink">
        {title} {badge}
      </h2>
      {children}
    </section>
  );
}

function FaultEditor({ faultKey }: { faultKey: string }) {
  const { draft } = useDraft();
  const fetcher = useCallback((v: number, signal: AbortSignal) => adminApi.fault(v, faultKey, signal), [faultKey]);
  const { state, reload } = useDraftData(fetcher);
  if (!draft || draft.building) return null;
  if (state.kind === "loading") return <p role="status">Loading the fault…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const f = state.data;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Link href={`/knowledge?draft=${draft.id}`} className="inline-flex min-h-11 items-center gap-1 self-start font-bold text-orange-text underline underline-offset-4">
          <ArrowLeft aria-hidden="true" className="size-4" /> All faults
        </Link>
        <h1 className="text-3xl font-black tracking-tight text-ink sm:text-4xl">
          <span className="font-mono">{f.key}</span> {f.fault.name}
        </h1>
        <p className="text-ink/75">Category {f.fault.category_code} · file {f.file_no}</p>
      </div>
      <Details f={f} onSaved={reload} />
      {LINE_TYPES.map((t) => (
        <Lines key={t.type} f={f} type={t.type} label={t.label} onSaved={reload} />
      ))}
      <Phrases f={f} onSaved={reload} />
      <Pictures f={f} onSaved={reload} />
      <SafetyRules f={f} onSaved={reload} />
      <DeleteFault f={f} />
    </div>
  );
}

// ---------------------------------------------------------------- details, applicability, weight

function Details({ f, onSaved }: { f: FaultDetail; onSaved: () => void }) {
  const { draft, writable, touched } = useDraft();
  const [status, setStatus] = useStatus();
  const form = useForm<FaultForm>({
    resolver: zodResolver(faultSchema),
    defaultValues: { ...f.fault, requires: requiresToForm(f.fault.requires), prior: f.fault.prior },
  });
  const reqs = useFieldArray({ control: form.control, name: "requires" });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (v) => {
    if (!draft) return;
    try {
      await adminApi.saveEdit(draft.id, "fault", f.key, { ...v, requires: requiresFromForm(v.requires), category_code: f.fault.category_code });
      setStatus({ kind: "saved", text: "Saved in the draft." });
      touched();
      onSaved();
    } catch (e) {
      setStatus({ kind: "error", text: errorMessage(e) });
    }
  });

  return (
    <Section title="Details" id="details-heading" badge={<EditedBadge show={f.fault_edit} />}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <fieldset disabled={!writable} className="grid gap-4 md:grid-cols-2">
          <TextInput label="Name" error={errors.name} className="md:col-span-2" {...form.register("name")} />
          <TextArea label="Description" error={errors.description} className="md:col-span-2" rows={4} {...form.register("description")} />
          <TextArea label="Likely fault" error={errors.likely_fault} {...form.register("likely_fault")} />
          <TextArea label="Where it is repaired" error={errors.repair_location} {...form.register("repair_location")} />
          <Select label="Repairable at the roadside" error={errors.road_repairable} options={["yes", "limited", "no", "unknown"].map((x) => ({ value: x, label: x }))} {...form.register("road_repairable")} />
          <TextInput label="Roadside repair (sheet wording)" error={errors.road_repairable_text} {...form.register("road_repairable_text")} />
          <TextArea label="Towing conditions" error={errors.towing_conditions_text} {...form.register("towing_conditions_text")} />
          <TextInput label="Repair time" error={errors.repair_time_text} {...form.register("repair_time_text")} />
          <Select
            label="Severity"
            error={errors.severity}
            options={[{ value: "", label: "Not set" }, ...["high", "medium", "low"].map((x) => ({ value: x, label: x }))]}
            {...form.register("severity", { setValueAs: (v) => (v ? v : null) })}
          />
          <TextInput
            label="Weight (engine v2 prior)"
            hint="How common this fault is compared with others (1 = average); empty = equal."
            type="number"
            step="0.1"
            error={errors.prior}
            {...form.register("prior", { setValueAs: numberOrNull })}
          />
          <Checkbox label="Safety critical" {...form.register("safety_critical")} />
        </fieldset>
        <fieldset disabled={!writable} className="flex flex-col gap-2">
          <legend className="font-semibold text-ink">Applicability: what the car must have</legend>
          <p className="text-sm text-ink/75">
            A feature (e.g. start_stop), fuels (e.g. diesel) or gearboxes (e.g. amt, cvt), comma separated. The engine ranks the fault lower when
            the car is known not to have it.
          </p>
          {reqs.fields.map((r, i) => (
            <div key={r.id} className="flex flex-wrap items-end gap-2">
              <Select label={`Requirement ${i + 1}`} options={REQUIREMENT_FIELDS.map((x) => ({ value: x, label: x }))} {...form.register(`requires.${i}.field`)} />
              <TextInput className="min-w-48 flex-1" label="Value" error={errors.requires?.[i]?.value} {...form.register(`requires.${i}.value`)} />
              <button type="button" aria-label={`Remove requirement ${i + 1}`} onClick={() => reqs.remove(i)} className="flex size-12 items-center justify-center rounded-full hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring focus-visible:outline-none">
                <Trash2 aria-hidden="true" className="size-5" />
              </button>
            </div>
          ))}
          <Button type="button" variant="outline" className="h-11 self-start rounded-full px-5 text-base" onClick={() => reqs.append({ field: "feature", value: "" })}>
            Add a requirement
          </Button>
        </fieldset>
        {writable && (
          <Button type="submit" size="cta" className="self-start" disabled={form.formState.isSubmitting}>
            Save details
          </Button>
        )}
        <SaveStatus status={status} />
      </form>
    </Section>
  );
}

// ---------------------------------------------------------------- lines

function Lines({ f, type, label, onSaved }: { f: FaultDetail; type: string; label: string; onSaved: () => void }) {
  const { draft, writable, touched } = useDraft();
  const item = f.items[type];
  const [status, setStatus] = useStatus();
  const form = useForm<z.infer<typeof linesSchema>>({
    resolver: zodResolver(linesSchema),
    defaultValues: { lines: item.lines.map((text) => ({ text })) },
  });
  const lines = useFieldArray({ control: form.control, name: "lines" });
  const errors = form.formState.errors;
  const submit = form.handleSubmit(async (v) => {
    if (!draft) return;
    try {
      await adminApi.saveEdit(draft.id, "fault_items", item.key, { lines: v.lines.map((l) => l.text) });
      form.reset(v);
      setStatus({ kind: "saved", text: "Saved in the draft." });
      touched();
      onSaved();
    } catch (e) {
      setStatus({ kind: "error", text: errorMessage(e) });
    }
  });
  const id = `lines-${type}`;
  return (
    <Section title={label} id={`${id}-heading`} badge={<EditedBadge show={item.edit} />}>
      <form onSubmit={submit} className="flex flex-col gap-3" noValidate aria-label={label}>
        <fieldset disabled={!writable} className="flex flex-col gap-2">
          {lines.fields.length === 0 && <p className="text-ink/70">None.</p>}
          {lines.fields.map((l, i) => (
            <div key={l.id} className="flex items-end gap-1">
              <TextInput className="flex-1" label={`${label.split(" (")[0]} ${i + 1}`} error={errors.lines?.[i]?.text} {...form.register(`lines.${i}.text`)} />
              <IconButton label={`Move line ${i + 1} up`} disabled={i === 0} onClick={() => lines.move(i, i - 1)}>
                <ArrowUp aria-hidden="true" className="size-5" />
              </IconButton>
              <IconButton label={`Move line ${i + 1} down`} disabled={i === lines.fields.length - 1} onClick={() => lines.move(i, i + 1)}>
                <ArrowDown aria-hidden="true" className="size-5" />
              </IconButton>
              <IconButton label={`Remove line ${i + 1}`} onClick={() => lines.remove(i)}>
                <Trash2 aria-hidden="true" className="size-5" />
              </IconButton>
            </div>
          ))}
        </fieldset>
        {writable && (
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="outline" className="h-11 rounded-full px-5 text-base" onClick={() => lines.append({ text: "" })}>
              Add a line
            </Button>
            <Button type="submit" className="h-11 rounded-full px-5 text-base font-bold" disabled={!form.formState.isDirty || form.formState.isSubmitting}>
              Save {label.split(" (")[0].toLowerCase()}
            </Button>
          </div>
        )}
        <SaveStatus status={status} />
      </form>
    </Section>
  );
}

function IconButton({ label, children, ...props }: { label: string; children: ReactNode; disabled?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      className="flex size-12 shrink-0 items-center justify-center rounded-full hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring focus-visible:outline-none disabled:opacity-40"
      {...props}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------- synonyms (customer phrases)

function Phrases({ f, onSaved }: { f: FaultDetail; onSaved: () => void }) {
  const { draft, writable, touched } = useDraft();
  const [status, setStatus] = useStatus();
  const form = useForm<z.infer<typeof phraseSchema>>({ resolver: zodResolver(phraseSchema), defaultValues: { text: "", language: "hinglish", english_gloss: "" } });
  const errors = form.formState.errors;

  async function run(action: () => Promise<unknown>, done: string) {
    try {
      await action();
      setStatus({ kind: "saved", text: done });
      touched();
      onSaved();
    } catch (e) {
      setStatus({ kind: "error", text: errorMessage(e) });
    }
  }

  const add = form.handleSubmit((v) =>
    run(async () => {
      const key = `${f.key}|${v.text.trim().split(/\s+/).join(" ").toLowerCase()}`;
      await adminApi.saveEdit(draft!.id, "phrase", key, { ...v, reviewed_by: null, reviewed_at: null });
      form.reset({ text: "", language: v.language, english_gloss: "" });
    }, "Phrase added to the draft."),
  );

  return (
    <Section title="Synonyms (customer phrases)" id="phrases-heading">
      <p className="text-sm text-ink/75">
        Ways customers describe this fault: Hinglish, English or Hindi (Devanagari). Held-out phrases are evaluation cases and cannot be changed.
      </p>
      <ul className="flex flex-col divide-y divide-border" aria-label="Phrases">
        {f.phrases.map((p) => (
          <li key={p.key} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="flex flex-col">
              <span className="font-semibold text-ink" lang={p.language === "hi" ? "hi" : undefined}>
                {p.text}
              </span>
              <span className="text-sm text-ink/75">
                {p.language} · {p.source}
                {p.english_gloss && <> · “{p.english_gloss}”</>}
                {p.held_out && " · held out (evaluation case)"}
                {p.reviewed_by && <> · reviewed by {p.reviewed_by}</>}
              </span>
            </span>
            <span className="flex flex-wrap items-center gap-2">
              <EditedBadge show={p.edit} />
              {p.pending_signoff && writable && (
                <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-sm" onClick={() => run(() => adminApi.signOff(draft!.id, "phrase", p.key), "Signed off.")}>
                  Sign off
                </Button>
              )}
              {writable && !p.held_out && (
                <IconButton label={`Delete phrase ${p.text}`} onClick={() => run(() => adminApi.saveEdit(draft!.id, "phrase", p.key, null), "Phrase deleted in the draft.")}>
                  <Trash2 aria-hidden="true" className="size-5" />
                </IconButton>
              )}
            </span>
          </li>
        ))}
      </ul>
      {f.deleted_phrases.length > 0 && <p className="text-sm text-ink/75">{f.deleted_phrases.length} phrase(s) deleted in this draft (revert them on the Changes tab).</p>}
      {writable && (
        <form onSubmit={add} className="grid gap-3 md:grid-cols-[2fr_1fr_2fr_auto] md:items-end" aria-label="Add a phrase" noValidate>
          <TextInput label="New phrase" error={errors.text} {...form.register("text")} />
          <Select label="Language" options={[{ value: "hinglish", label: "Hinglish" }, { value: "hi", label: "Hindi (Devanagari)" }, { value: "en", label: "English" }]} {...form.register("language")} />
          <TextInput label="English meaning" error={errors.english_gloss} {...form.register("english_gloss")} />
          <Button type="submit" className="h-12 rounded-full px-5 text-base font-bold">
            Add phrase
          </Button>
        </form>
      )}
      <SaveStatus status={status} />
    </Section>
  );
}

// ---------------------------------------------------------------- pictures

function Pictures({ f, onSaved }: { f: FaultDetail; onSaved: () => void }) {
  const { draft, writable, touched } = useDraft();
  const [images, setImages] = useState(f.images);
  const [status, setStatus] = useStatus();
  const [picking, setPicking] = useState(false);
  const [library, setLibrary] = useState<FaultDetail["images"] | null>(null);
  const dirty = images.map((i) => i.sha1).join() !== f.images.map((i) => i.sha1).join();

  async function save() {
    try {
      await adminApi.saveEdit(draft!.id, "fault_images", f.key, { images: images.map((i) => i.sha1) });
      setStatus({ kind: "saved", text: "Pictures saved in the draft." });
      touched();
      onSaved();
    } catch (e) {
      setStatus({ kind: "error", text: errorMessage(e) });
    }
  }

  return (
    <Section title="Pictures (media references)" id="pictures-heading" badge={<EditedBadge show={f.images_edit} />}>
      {images.length === 0 && <p className="text-ink/70">No pictures. The first one is the main picture.</p>}
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Pictures">
        {images.map((img, i) => (
          <li key={img.sha1} className="flex flex-col gap-2 rounded-2xl border border-border p-2">
            {/* eslint-disable-next-line @next/next/no-img-element -- dataset pictures served by the API */}
            <img src={mediaUrl(img.url)} alt={img.caption ?? `Picture ${i + 1} of ${f.key}`} className="aspect-square w-full rounded-xl object-contain" />
            {i === 0 && <span className="text-sm font-bold text-orange-text">Main picture</span>}
            {writable && (
              <span className="flex gap-1">
                {i > 0 && (
                  <IconButton label={`Make picture ${i + 1} the main one`} onClick={() => setImages([img, ...images.filter((x) => x !== img)])}>
                    <Star aria-hidden="true" className="size-5" />
                  </IconButton>
                )}
                <IconButton label={`Remove picture ${i + 1}`} onClick={() => setImages(images.filter((x) => x !== img))}>
                  <Trash2 aria-hidden="true" className="size-5" />
                </IconButton>
              </span>
            )}
          </li>
        ))}
      </ul>
      {writable && (
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            variant="outline"
            className="h-11 rounded-full px-5 text-base"
            onClick={() => {
              setPicking(true);
              adminApi.images(f.file_no).then(setLibrary).catch((e) => setStatus({ kind: "error", text: errorMessage(e) }));
            }}
          >
            <ImagePlus aria-hidden="true" className="size-5" /> Add a picture from file {f.file_no}
          </Button>
          <Button type="button" className="h-11 rounded-full px-5 text-base font-bold" disabled={!dirty} onClick={() => void save()}>
            Save pictures
          </Button>
        </div>
      )}
      <SaveStatus status={status} />
      <Dialog open={picking} onOpenChange={setPicking} title={`Pictures in file ${f.file_no}`} className="max-w-3xl">
        {!library && <p role="status">Loading pictures…</p>}
        {library && library.length === 0 && <p>No pictures in this file. Uploading new pictures comes with Parts &amp; Prices (part 2).</p>}
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {library
            ?.filter((x) => !images.some((i) => i.sha1 === x.sha1))
            .map((img) => (
              <li key={img.sha1}>
                <button
                  type="button"
                  onClick={() => {
                    setImages([...images, img]);
                    setPicking(false);
                  }}
                  className="flex w-full flex-col gap-1 rounded-2xl border border-border p-2 text-left focus-visible:ring-3 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- dataset pictures served by the API */}
                  <img src={mediaUrl(img.url)} alt="" className="aspect-square w-full rounded-xl object-contain" />
                  <span className="text-xs text-ink/75">{img.caption ?? img.url.split("/").pop()}</span>
                </button>
              </li>
            ))}
        </ul>
      </Dialog>
    </Section>
  );
}

// ---------------------------------------------------------------- safety rules and delete

function SafetyRules({ f, onSaved }: { f: FaultDetail; onSaved: () => void }) {
  const { draft, writable, touched } = useDraft();
  const [editing, setEditing] = useState<SafetyRuleRow | null>(null);
  const [status, setStatus] = useStatus();
  return (
    <Section title="Safety rules" id="safety-heading">
      {f.safety_rules.length === 0 && <p className="text-ink/70">This fault has no safety rule.</p>}
      <ul className="flex flex-col gap-3" aria-label="Safety rules">
        {f.safety_rules.map((r) => (
          <li key={r.key} className="flex flex-col gap-2 rounded-2xl border border-border p-3">
            <p className="flex flex-wrap items-center gap-2 font-bold text-ink">
              {r.risk_level} risk · {SAFETY_STATUS[r.status]} <EditedBadge show={r.edit} />
            </p>
            {r.stop_driving_trigger && <p className="text-ink">Stop driving: {r.stop_driving_trigger}</p>}
            {r.roadside_action && <p className="text-ink">Roadside: {r.roadside_action}</p>}
            <p className="text-sm text-ink/75">
              {r.source} · {r.signed_off_by ? `signed off by ${r.signed_off_by}` : "not signed off"}
            </p>
            {writable && (
              <span className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" className="h-11 rounded-full px-4 text-base" onClick={() => setEditing(r)}>
                  Edit rule
                </Button>
                {r.status === "active_pending_signoff" && (
                  <Button
                    type="button"
                    variant="outline"
                    className="h-11 rounded-full px-4 text-base"
                    onClick={() =>
                      adminApi
                        .signOff(draft!.id, "safety_rule", r.key)
                        .then(() => {
                          setStatus({ kind: "saved", text: "Signed off: the rule is approved in the draft." });
                          touched();
                          onSaved();
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
      {editing && <SafetyRuleDialog rule={editing} open onOpenChange={(o) => !o && setEditing(null)} onSaved={onSaved} />}
    </Section>
  );
}

function DeleteFault({ f }: { f: FaultDetail }) {
  const { draft, writable, touched } = useDraft();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  if (!writable) return null;
  return (
    <section className="flex flex-col items-start gap-2">
      <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base font-bold" onClick={() => setOpen(true)}>
        Delete this fault
      </Button>
      <Dialog open={open} onOpenChange={setOpen} title={`Delete ${f.key}?`}>
        <p className="text-ink">
          It is removed from this draft with its lines, phrases and safety rules. A later Excel import brings it back from the file, and this
          edit removes it again (shown as a conflict if the file changed it).
        </p>
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            size="cta"
            onClick={() =>
              adminApi
                .saveEdit(draft!.id, "fault", f.key, null, "deleted in the editor")
                .then(() => {
                  touched();
                  router.push(`/knowledge?draft=${draft!.id}`);
                })
                .catch((e) => setError(errorMessage(e)))
            }
          >
            Delete fault
          </Button>
          <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base" onClick={() => setOpen(false)}>
            Keep it
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
