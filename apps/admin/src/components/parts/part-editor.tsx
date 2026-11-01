"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";

import { Button } from "@im/ui/button";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { EditedBadge, numberOrNull, SaveStatus, Select, TextInput, useStatus } from "@/components/form";
import { DraftProvider, useDraft, useDraftData } from "@/components/knowledge/draft";
import { BLANK_PART, inr, PartFields } from "@/components/parts/parts-view";
import { PriceDialog } from "@/components/parts/price-dialog";
import { UploadPicture } from "@/components/upload-picture";
import { adminApi, type Catalogue, errorMessage, type FitRow, mediaUrl, type PartDetail, type Picture, type PriceRow } from "@/lib/api";
import { date } from "@/lib/format";
import { type FitForm, fitSchema, FUELS, type PartForm, partSchema, TRANSMISSIONS } from "@/lib/schemas";

export function PartEditorPage({ partKey }: { partKey: string }) {
  return (
    <DraftProvider>
      <PartEditor partKey={partKey} />
    </DraftProvider>
  );
}

function PartEditor({ partKey }: { partKey: string }) {
  const { draft } = useDraft();
  const { state, reload } = useDraftData(useCallback((v: number, s: AbortSignal) => adminApi.part(v, partKey, s), [partKey]));
  if (!draft || draft.building) return null;
  if (state.kind === "loading") return <p role="status">Loading the part…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const p = state.data;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Link href={`/parts?draft=${draft.id}`} className="inline-flex min-h-11 items-center gap-1 self-start font-bold text-orange-text underline underline-offset-4">
          <ArrowLeft aria-hidden="true" className="size-4" /> All parts
        </Link>
        <h1 className="text-3xl font-black tracking-tight text-ink sm:text-4xl">{p.part.description}</h1>
        <p className="text-ink/75">{p.key}</p>
      </div>
      <Details p={p} onSaved={reload} />
      <Pictures key={p.images.map((i) => i.sha1).join()} p={p} onSaved={reload} />
      <Prices p={p} onSaved={reload} />
      <Fits p={p} onSaved={reload} />
    </div>
  );
}

function Card({ title, id, children, badge }: { title: string; id: string; children: React.ReactNode; badge?: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-4 sm:p-5">
      <h2 id={id} className="flex flex-wrap items-center gap-2 text-xl font-black text-ink">
        {title} {badge}
      </h2>
      {children}
    </section>
  );
}

function Details({ p, onSaved }: { p: PartDetail; onSaved: () => void }) {
  const { draft, writable, touched } = useDraft();
  const [status, setStatus] = useStatus();
  const form = useForm<PartForm>({ resolver: zodResolver(partSchema), defaultValues: { ...BLANK_PART, ...p.part } });
  const submit = form.handleSubmit(async (v) => {
    try {
      await adminApi.saveEdit(draft!.id, "part", p.key, v);
      setStatus({ kind: "saved", text: "Saved in the draft (the shared parts list changes at publish)." });
      touched();
      onSaved();
    } catch (e) {
      setStatus({ kind: "error", text: errorMessage(e) });
    }
  });
  return (
    <Card title="Details" id="part-details" badge={<EditedBadge show={p.part_edit} />}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <fieldset disabled={!writable}>
          <PartFields form={form} />
        </fieldset>
        {writable && (
          <Button type="submit" size="cta" className="self-start">
            Save details
          </Button>
        )}
        <SaveStatus status={status} />
      </form>
    </Card>
  );
}

function Pictures({ p, onSaved }: { p: PartDetail; onSaved: () => void }) {
  const { draft, writable, touched } = useDraft();
  const [images, setImages] = useState<Picture[]>(p.images);
  const [status, setStatus] = useStatus();
  const dirty = images.map((i) => i.sha1).join() !== p.images.map((i) => i.sha1).join();
  return (
    <Card title="Pictures" id="part-pictures" badge={<EditedBadge show={p.images_edit} />}>
      {images.length === 0 && <p className="text-ink/70">No pictures.</p>}
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Part pictures">
        {images.map((img, i) => (
          <li key={img.sha1} className="flex flex-col gap-2 rounded-2xl border border-border p-2">
            {/* eslint-disable-next-line @next/next/no-img-element -- pictures served by the API */}
            <img src={mediaUrl(img.url)} alt={img.caption ?? `Picture ${i + 1}`} className="aspect-square w-full rounded-xl object-contain" />
            {writable && (
              <button
                type="button"
                aria-label={`Remove picture ${i + 1}`}
                onClick={() => setImages(images.filter((x) => x !== img))}
                className="flex size-11 items-center justify-center rounded-full hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring focus-visible:outline-none"
              >
                <Trash2 aria-hidden="true" className="size-5" />
              </button>
            )}
          </li>
        ))}
      </ul>
      {writable && (
        <div className="flex flex-wrap gap-3">
          <UploadPicture onUploaded={(img) => setImages([...images, img])} />
          <Button
            type="button"
            className="h-11 rounded-full px-5 text-base font-bold"
            disabled={!dirty}
            onClick={() =>
              adminApi
                .saveEdit(draft!.id, "part_images", p.key, { images: images.map((i) => i.sha1) })
                .then(() => {
                  setStatus({ kind: "saved", text: "Pictures saved in the draft." });
                  touched();
                  onSaved();
                })
                .catch((e) => setStatus({ kind: "error", text: errorMessage(e) }))
            }
          >
            Save pictures
          </Button>
        </div>
      )}
      <SaveStatus status={status} />
    </Card>
  );
}

function Prices({ p, onSaved }: { p: PartDetail; onSaved: () => void }) {
  const { writable } = useDraft();
  const [editing, setEditing] = useState<PriceRow | "new" | null>(null);
  const [status, setStatus] = useStatus();
  return (
    <Card title="Prices" id="part-prices">
      {p.prices.length === 0 && <p className="text-ink/70">No prices yet.</p>}
      <ul className="flex flex-col gap-2" aria-label="Prices">
        {p.prices.map((r) => (
          <li key={r.key} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border p-3">
            <span className="flex flex-col">
              <span className="font-bold text-ink">
                {r.segment}: {inr(r.price_inr)}
                {r.price_max_inr ? `–${inr(r.price_max_inr)}` : ""}
              </span>
              <span className="text-sm text-ink/75">
                {r.supplier || r.source_url || "no source"} · {r.checked_on ? date(r.checked_on) : "no date"} · {r.verification_status}
                {r.second_look_by && ` · checked by ${r.second_look_by}`}
              </span>
            </span>
            <span className="flex flex-wrap items-center gap-2">
              {r.flagged && <EditedBadge show label="₹20,000+: second look" />}
              <EditedBadge show={r.edit} />
              {writable && (
                <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => setEditing(r)}>
                  Edit
                </Button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {writable && (
        <Button type="button" variant="outline" className="h-11 self-start rounded-full px-4 text-base" onClick={() => setEditing("new")}>
          <Plus aria-hidden="true" className="size-5" /> Add a price
        </Button>
      )}
      <SaveStatus status={status} />
      {editing && (
        <PriceDialog
          partKey={p.key}
          row={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(warning) => {
            setStatus({ kind: "saved", text: warning ?? "Saved in the draft." });
            setEditing(null);
            onSaved();
          }}
        />
      )}
    </Card>
  );
}

function Fits({ p, onSaved }: { p: PartDetail; onSaved: () => void }) {
  const { writable } = useDraft();
  const [editing, setEditing] = useState<FitRow | "new" | null>(null);
  const [status, setStatus] = useStatus();
  return (
    <Card title="Fits (compatibility)" id="part-fits">
      {p.fits.length === 0 && <p className="text-ink/70">No cars listed for this part.</p>}
      <ul className="flex flex-col gap-2" aria-label="Fits">
        {p.fits.map((f) => (
          <li key={f.key} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border p-3">
            <span className="flex flex-col">
              <span className="font-bold text-ink">
                {f.model} {f.year_from ? `${f.year_from}–${f.year_to ?? ""}` : ""} {f.fuel ?? ""} {f.transmission ?? ""}
              </span>
              <span className="text-sm text-ink/75">
                {f.fit_text} · {f.verification_status === "confirm_fit" ? "confirm by VIN" : "listed"}
              </span>
            </span>
            <span className="flex items-center gap-2">
              <EditedBadge show={f.edit} />
              {writable && (
                <Button type="button" variant="outline" className="h-10 rounded-full px-3 text-sm" onClick={() => setEditing(f)}>
                  Edit
                </Button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {writable && (
        <Button type="button" variant="outline" className="h-11 self-start rounded-full px-4 text-base" onClick={() => setEditing("new")}>
          <Plus aria-hidden="true" className="size-5" /> Add a car it fits
        </Button>
      )}
      <SaveStatus status={status} />
      {editing && (
        <FitDialog
          partKey={p.key}
          row={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(text) => {
            setStatus({ kind: "saved", text });
            setEditing(null);
            onSaved();
          }}
        />
      )}
    </Card>
  );
}

function FitDialog({ partKey, row, onClose, onSaved }: { partKey: string; row: FitRow | null; onClose: () => void; onSaved: (t: string) => void }) {
  const { draft, touched } = useDraft();
  const [cat, setCat] = useState<Catalogue | null>(null);
  const [makeId, setMakeId] = useState<number | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    adminApi
      .catalogue()
      .then((c) => {
        setCat(c);
        if (row) setMakeId(c.makes.find((m) => m.models.some((x) => x.id === row.model_id))?.id ?? null);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [row]);
  const form = useForm<FitForm>({
    resolver: zodResolver(fitSchema),
    defaultValues: {
      model_id: row?.model_id ?? (undefined as unknown as number),
      year_from: row?.year_from ?? null,
      year_to: row?.year_to ?? null,
      fuel: (row?.fuel as FitForm["fuel"]) ?? null,
      transmission: (row?.transmission as FitForm["transmission"]) ?? null,
      verification_status: (row?.verification_status as FitForm["verification_status"]) ?? "listed",
      fit_text: row?.fit_text ?? "",
      source_url: row?.source_url ?? "",
    },
  });
  const e = form.formState.errors;
  const modelId = useWatch({ control: form.control, name: "model_id" });
  const make = cat?.makes.find((m) => m.id === makeId);
  const save = (data: unknown, text: string) =>
    adminApi
      .saveEdit(draft!.id, "part_fit", row ? row.key : `${partKey}|`, data)
      .then(() => {
        touched();
        onSaved(text);
      })
      .catch((err) => setError(errorMessage(err)));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={row ? "Edit fit" : "Add a car it fits"} className="max-w-2xl">
      <form onSubmit={form.handleSubmit((v) => save(v, "Fit saved in the draft."))} className="flex flex-col gap-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1 font-semibold text-ink">
            Make
            <select className="h-12 rounded-xl border border-input bg-white px-4" value={makeId ?? ""} disabled={!!row} onChange={(ev) => setMakeId(Number(ev.target.value) || null)}>
              <option value="">Choose a make</option>
              {cat?.makes.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          <Select
            label="Model"
            disabled={!!row}
            error={e.model_id}
            value={modelId ? String(modelId) : ""}
            options={[{ value: "", label: "Choose a model" }, ...(make?.models.map((m) => ({ value: String(m.id), label: m.name })) ?? [])]}
            {...form.register("model_id", { setValueAs: numberOrNull })}
          />
          <TextInput label="From year (optional)" type="number" error={e.year_from} {...form.register("year_from", { setValueAs: numberOrNull })} />
          <TextInput label="To year (optional)" type="number" error={e.year_to} {...form.register("year_to", { setValueAs: numberOrNull })} />
          <Select label="Fuel (optional)" options={[{ value: "", label: "any" }, ...FUELS.map((f) => ({ value: f, label: f }))]} {...form.register("fuel", { setValueAs: (v) => v || null })} />
          <Select label="Gearbox (optional)" options={[{ value: "", label: "any" }, ...TRANSMISSIONS.map((t) => ({ value: t, label: t }))]} {...form.register("transmission", { setValueAs: (v) => v || null })} />
          <Select
            label="How sure"
            options={[
              { value: "listed", label: "listed for this model" },
              { value: "confirm_fit", label: "confirm by chassis number (VIN)" },
            ]}
            {...form.register("verification_status")}
          />
          <TextInput label="Source link" type="url" error={e.source_url} {...form.register("source_url")} />
        </div>
        <TextInput label="What the source says" error={e.fit_text} {...form.register("fit_text")} />
        {error && (
          <p role="alert" className="font-semibold text-orange-text">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" size="cta">
            Save fit in draft
          </Button>
          {row && (
            <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base" onClick={() => void save(null, "Fit removed in the draft.")}>
              Remove fit
            </Button>
          )}
        </div>
      </form>
    </Dialog>
  );
}
