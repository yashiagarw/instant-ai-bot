"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { ArrowLeft, FileText, Plus, Trash2 } from "lucide-react";

import { Button } from "@im/ui/button";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { Field } from "@/components/field";
import { SaveStatus, Select, useStatus } from "@/components/form";
import { type MapCircle, type MapPoint, MapView } from "@/components/map-view";
import { DutySwitch, MechanicFields, useCategories } from "@/components/mechanics/mechanics-view";
import { useMe } from "@/components/staff-shell";
import { adminApi, type DocumentKind, errorMessage, type Mechanic, type MechanicDocument, type Precision, type Shift, type ZoneInput } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { precisionNote, shiftProblem, WEEKDAYS } from "@/lib/ops";
import { type MechanicForm, mechanicSchema } from "@/lib/schemas";
import { useLoad } from "@/lib/use-load";

export function MechanicEditor({ id }: { id: number }) {
  const { me } = useMe();
  const manage = me.permissions.includes("mechanics.manage");
  const { state, reload, set } = useLoad(useCallback((s: AbortSignal) => adminApi.mechanic(id, s), [id]));
  const added = useSearchParams().get("added") === "1";

  if (state.kind === "loading") return <p role="status">Loading the mechanic…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const m = state.data;

  return (
    <div className="flex flex-col gap-6">
      <Link href="/mechanics" className="inline-flex min-h-11 items-center gap-2 self-start font-semibold text-orange-text underline underline-offset-4">
        <ArrowLeft aria-hidden="true" className="size-4" /> All mechanics
      </Link>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-3xl font-black tracking-tight text-ink sm:text-4xl">{m.name}</h1>
          <p className="text-ink/80">
            <a href={`tel:${m.phone}`} className="font-semibold text-orange-text underline underline-offset-4">
              {m.phone}
            </a>
            {" · "}
            {m.jobs_today} of {m.max_jobs_per_day} jobs today
            {m.dev_seed && <span className="ml-2 font-bold text-amber-text">Fake (development seed)</span>}
          </p>
        </div>
        <DutySwitch mechanic={m} onChange={manage ? set : undefined} />
      </header>
      {added && (
        <p role="status" className="font-semibold text-success">
          Mechanic added. Set their skills, zones and shifts below.
        </p>
      )}
      <Details mechanic={m} manage={manage} onSaved={set} />
      <Skills mechanic={m} manage={manage} onSaved={set} />
      <Zones mechanic={m} manage={manage} onSaved={set} />
      <Shifts mechanic={m} manage={manage} onSaved={set} />
      {me.permissions.includes("mechanics.documents") && <Documents mechanic={m} />}
    </div>
  );
}

function Section({ title, children, intro }: { title: string; children: ReactNode; intro?: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-4 sm:p-6">
      <div className="flex flex-col gap-1">
        <h2 id={id} className="text-xl font-black text-ink">
          {title}
        </h2>
        {intro && <div className="text-sm text-ink/80">{intro}</div>}
      </div>
      {children}
    </section>
  );
}

type Saved = { mechanic: Mechanic; manage: boolean; onSaved: (m: Mechanic) => void };

function useSave(onSaved: (m: Mechanic) => void) {
  const [status, setStatus] = useStatus();
  const [busy, setBusy] = useState(false);
  const save = useCallback(
    async (fn: () => Promise<Mechanic>, done: string) => {
      setBusy(true);
      setStatus({ kind: "idle" });
      try {
        onSaved(await fn());
        setStatus({ kind: "saved", text: done });
      } catch (e) {
        setStatus({ kind: "error", text: errorMessage(e) });
      } finally {
        setBusy(false);
      }
    },
    [onSaved, setStatus],
  );
  return { status, setStatus, busy, save };
}

// ---------------------------------------------------------------- details

function Details({ mechanic: m, manage, onSaved }: Saved) {
  const { status, save } = useSave(onSaved);
  const form = useForm<MechanicForm>({
    resolver: zodResolver(mechanicSchema),
    values: {
      name: m.name,
      phone: m.phone,
      base_pincode: m.base_pincode,
      base_area: m.base_area,
      rating: m.rating,
      max_jobs_per_day: m.max_jobs_per_day,
      active: m.active,
      notes: m.notes,
    },
  });
  const submit = form.handleSubmit((v) => save(() => adminApi.saveMechanic(m.id, v), "Details saved."));
  return (
    <Section title="Details">
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <fieldset disabled={!manage} className="contents">
          <MechanicFields form={form} />
        </fieldset>
        {manage && (
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={form.formState.isSubmitting} className="h-12 rounded-full px-6 text-lg font-bold">
              Save details
            </Button>
            <SaveStatus status={status} />
          </div>
        )}
      </form>
    </Section>
  );
}

// ---------------------------------------------------------------- skills

function Skills({ mechanic: m, manage, onSaved }: Saved) {
  const categories = useCategories();
  const [chosen, setChosen] = useState<string[]>(m.skills);
  const { status, busy, save } = useSave(onSaved);
  const options = useMemo(() => {
    const known = categories.list.map((c) => ({ code: c.code, name: c.name }));
    // Skills of categories the list no longer has stay visible (and removable).
    for (const code of m.skills) if (!known.some((k) => k.code === code)) known.push({ code, name: code });
    return known;
  }, [categories.list, m.skills]);

  return (
    <Section title="Skills" intro="The problem categories this mechanic handles. A request is matched on its diagnosis's category.">
      {categories.failed && <ErrorBox message="We couldn't load the category names. The codes are shown instead." />}
      <fieldset disabled={!manage} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <legend className="sr-only">Skills</legend>
        {options.map((c) => (
          <label key={c.code} className="flex min-h-11 items-center gap-3 rounded-xl border border-border px-3 font-semibold text-ink">
            <input
              type="checkbox"
              className="size-5 shrink-0 accent-cta"
              checked={chosen.includes(c.code)}
              onChange={(e) => setChosen(e.target.checked ? [...chosen, c.code] : chosen.filter((x) => x !== c.code))}
            />
            {c.name}
          </label>
        ))}
      </fieldset>
      {manage && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            disabled={busy}
            className="h-12 rounded-full px-6 text-lg font-bold"
            onClick={() => save(() => adminApi.setSkills(m.id, chosen), `Skills saved (${chosen.length}).`)}
          >
            Save skills
          </Button>
          <SaveStatus status={status} />
        </div>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------- zones

type ZoneRow = ZoneInput & { point?: [number, number] | null; precision?: Precision | null };

function zoneLabel(z: ZoneRow): string {
  if (z.pincode) return `Pincode ${z.pincode}`;
  const where = z.center_lat !== null && z.center_lon !== null ? `around ${z.center_lat}, ${z.center_lon}` : "around the base";
  return `${z.radius_km} km ${where}`;
}

function Zones({ mechanic: m, manage, onSaved }: Saved) {
  const [zones, setZones] = useState<ZoneRow[]>(m.zones);
  const [shownFor, setShownFor] = useState(m.zones);
  if (shownFor !== m.zones) {
    setShownFor(m.zones); // saved: show what the server stored (with the pincodes' points)
    setZones(m.zones);
  }
  const { status, setStatus, busy, save } = useSave(onSaved);
  const [pincode, setPincode] = useState("");
  const [radius, setRadius] = useState("5");
  const [centre, setCentre] = useState<{ lat: string; lon: string }>({ lat: "", lon: "" });
  const [error, setError] = useState("");

  const base = m.base_point;
  const points: MapPoint[] = [
    ...(base ? [{ id: "base", lat: base[0], lon: base[1], label: `Base: ${m.base_area || m.base_pincode}`, tone: "mechanic" as const, rough: m.base_precision !== "pincode" }] : []),
    ...zones.flatMap((z, i) =>
      z.pincode && z.point ? [{ id: `z${i}`, lat: z.point[0], lon: z.point[1], label: `Pincode ${z.pincode}`, tone: "zone" as const, rough: z.precision !== "pincode" }] : [],
    ),
  ];
  const circles: MapCircle[] = zones.flatMap((z, i) => {
    if (z.radius_km === null) return [];
    const c = z.center_lat !== null && z.center_lon !== null ? [z.center_lat, z.center_lon] : base;
    return c ? [{ id: `r${i}`, lat: c[0], lon: c[1], radiusKm: z.radius_km, label: zoneLabel(z) }] : [];
  });

  function addPincode(e: FormEvent) {
    e.preventDefault();
    const pin = pincode.trim();
    if (!/^\d{6}$/.test(pin)) return setError("A pincode has 6 digits.");
    if (zones.some((z) => z.pincode === pin)) return setError("That pincode is already a zone.");
    setError("");
    setZones([...zones, { pincode: pin, radius_km: null, center_lat: null, center_lon: null }]);
    setPincode("");
    setStatus({ kind: "idle" });
  }

  function addRadius(e: FormEvent) {
    e.preventDefault();
    const km = Number(radius);
    if (!(km >= 0.5 && km <= 100)) return setError("A radius is 0.5 to 100 km.");
    const hasCentre = centre.lat !== "" || centre.lon !== "";
    const lat = Number(centre.lat);
    const lon = Number(centre.lon);
    if (hasCentre && !(lat >= 28 && lat <= 29.5 && lon >= 76.5 && lon <= 78)) {
      return setError("The centre must be in Delhi NCR (latitude 28 to 29.5, longitude 76.5 to 78), or leave both empty for the base.");
    }
    setError("");
    setZones([...zones, { pincode: null, radius_km: km, center_lat: hasCentre ? lat : null, center_lon: hasCentre ? lon : null }]);
    setCentre({ lat: "", lon: "" });
    setStatus({ kind: "idle" });
  }

  return (
    <Section
      title="Zones"
      intro="Where this mechanic works: pincodes, or a radius around their base or a point. Points are pincode centres (approximate); a dashed point is a rough location."
    >
      <MapView
        label={`${m.name}'s zones`}
        points={points}
        circles={circles}
        onPick={manage ? (lat, lon) => setCentre({ lat: String(lat), lon: String(lon) }) : undefined}
      />
      {base && precisionNote(m.base_precision) && (
        <p className="text-sm font-semibold text-amber-text">
          Base {m.base_pincode}: {precisionNote(m.base_precision)} (distances from it can be several km off).
        </p>
      )}
      <ul aria-label="Zones" className="flex flex-col gap-2">
        {zones.length === 0 && <li className="text-ink/80">No zones: this mechanic is never suggested.</li>}
        {zones.map((z, i) => (
          <li key={`${z.pincode ?? "r"}-${i}`} className="flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-xl border border-border px-3 py-1">
            <span>
              <span className="font-semibold">{zoneLabel(z)}</span>
              {z.pincode && precisionNote(z.precision) && (
                <span className="ml-2 text-sm font-semibold text-amber-text">({precisionNote(z.precision)})</span>
              )}
              {z.pincode && z.point === undefined && <span className="ml-2 text-sm text-ink/75">(not saved yet)</span>}
            </span>
            {manage && (
              <button
                type="button"
                aria-label={`Remove ${zoneLabel(z)}`}
                onClick={() => setZones(zones.filter((_, j) => j !== i))}
                className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
              >
                <Trash2 aria-hidden="true" className="size-4" /> Remove
              </button>
            )}
          </li>
        ))}
      </ul>
      {manage && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <form onSubmit={addPincode} noValidate className="flex flex-col gap-2 rounded-2xl bg-warm-white p-4">
              <Field label="Pincode" inputMode="numeric" maxLength={6} value={pincode} onChange={(e) => setPincode(e.target.value)} />
              <Button type="submit" variant="outline" className="h-11 self-start rounded-full px-5 text-base font-bold">
                <Plus aria-hidden="true" className="size-4" /> Add pincode
              </Button>
            </form>
            <form onSubmit={addRadius} noValidate className="flex flex-col gap-2 rounded-2xl bg-warm-white p-4">
              <Field label="Radius (km)" type="number" step="0.5" value={radius} onChange={(e) => setRadius(e.target.value)} />
              <p className="text-sm text-ink/80">Centre: empty = the base. Click the map, or type it.</p>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Latitude" inputMode="decimal" value={centre.lat} onChange={(e) => setCentre({ ...centre, lat: e.target.value })} />
                <Field label="Longitude" inputMode="decimal" value={centre.lon} onChange={(e) => setCentre({ ...centre, lon: e.target.value })} />
              </div>
              <Button type="submit" variant="outline" className="h-11 self-start rounded-full px-5 text-base font-bold">
                <Plus aria-hidden="true" className="size-4" /> Add radius
              </Button>
            </form>
          </div>
          {error && (
            <p role="alert" className="font-semibold text-orange-text">
              {error}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              disabled={busy}
              className="h-12 rounded-full px-6 text-lg font-bold"
              onClick={() =>
                save(
                  () => adminApi.setZones(m.id, zones.map(({ pincode, radius_km, center_lat, center_lon }) => ({ pincode, radius_km, center_lat, center_lon }))),
                  `Zones saved (${zones.length}).`,
                )
              }
            >
              Save zones
            </Button>
            <SaveStatus status={status} />
          </div>
        </>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------- shifts

function Shifts({ mechanic: m, manage, onSaved }: Saved) {
  const [shifts, setShifts] = useState<Shift[]>(m.shifts);
  const { status, setStatus, busy, save } = useSave(onSaved);
  const update = (i: number, patch: Partial<Shift>) => setShifts(shifts.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  return (
    <Section title="Weekly shifts" intro="India time. No shifts = any time while on duty. Split an overnight shift at midnight.">
      <div className="flex flex-col gap-3">
        {WEEKDAYS.map((day, d) => {
          const rows = shifts.map((s, i) => ({ s, i })).filter((x) => x.s.weekday === d);
          return (
            <fieldset key={day} disabled={!manage} className="flex flex-col gap-2 rounded-2xl border border-border p-3">
              <legend className="px-1 font-bold text-ink">{day}</legend>
              {rows.length === 0 && <p className="text-sm text-ink/75">No shift</p>}
              {rows.map(({ s, i }, n) => (
                <div key={i} className="flex flex-wrap items-end gap-2">
                  <Field label={`${day} shift ${n + 1} starts`} type="time" value={s.start_time} onChange={(e) => update(i, { start_time: e.target.value })} />
                  <Field label={`${day} shift ${n + 1} ends`} type="time" value={s.end_time} onChange={(e) => update(i, { end_time: e.target.value })} />
                  {manage && (
                    <button
                      type="button"
                      aria-label={`Remove ${day} shift ${n + 1}`}
                      onClick={() => setShifts(shifts.filter((_, j) => j !== i))}
                      className="inline-flex min-h-12 items-center rounded-full px-3 font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
                    >
                      <Trash2 aria-hidden="true" className="size-4" />
                    </button>
                  )}
                </div>
              ))}
              {manage && (
                <button
                  type="button"
                  onClick={() => setShifts([...shifts, { weekday: d, start_time: "09:00", end_time: "18:00" }])}
                  className="inline-flex min-h-11 items-center gap-1 self-start rounded-full border border-border px-3 text-sm font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
                >
                  <Plus aria-hidden="true" className="size-4" /> Add {day} shift
                </button>
              )}
            </fieldset>
          );
        })}
      </div>
      {manage && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            disabled={busy}
            className="h-12 rounded-full px-6 text-lg font-bold"
            onClick={() => {
              const problem = shiftProblem(shifts);
              if (problem) return setStatus({ kind: "error", text: problem });
              void save(() => adminApi.setShifts(m.id, shifts), shifts.length ? `Shifts saved (${shifts.length}).` : "Saved: any time while on duty.");
            }}
          >
            Save shifts
          </Button>
          <SaveStatus status={status} />
        </div>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------- documents (super admins)

const KINDS: { value: DocumentKind; label: string }[] = [
  { value: "id_proof", label: "ID proof" },
  { value: "driving_licence", label: "Driving licence" },
  { value: "certificate", label: "Certificate" },
  { value: "other", label: "Other" },
];

function Documents({ mechanic: m }: { mechanic: Mechanic }) {
  const { state, reload, set } = useLoad(useCallback((s: AbortSignal) => adminApi.documents(m.id, s), [m.id]));
  const [kind, setKind] = useState<DocumentKind>("id_proof");
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useStatus();
  const [deleting, setDeleting] = useState<MechanicDocument | null>(null);
  const docs = state.kind === "ready" ? state.data : [];

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) return setStatus({ kind: "error", text: "Choose a file." });
    try {
      const d = await adminApi.uploadDocument(m.id, kind, file);
      set([...docs, d]);
      setFile(null);
      (e.target as HTMLFormElement).reset();
      setStatus({ kind: "saved", text: `${d.filename} stored (encrypted).` });
    } catch (err) {
      setStatus({ kind: "error", text: errorMessage(err) });
    }
  }

  return (
    <Section title="Documents" intro="Super admins only. Stored encrypted; every view is written to the audit log.">
      {state.kind === "loading" && <p role="status">Loading documents…</p>}
      {state.kind === "error" && <ErrorBox message={state.message} onRetry={reload} />}
      {state.kind === "ready" && (
        <ul aria-label="Documents" className="flex flex-col gap-2">
          {docs.length === 0 && <li className="text-ink/80">No documents.</li>}
          {docs.map((d) => (
            <li key={d.id} className="flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-xl border border-border px-3 py-1">
              <span>
                <span className="font-semibold">{KINDS.find((k) => k.value === d.kind)?.label}</span>: {d.filename}
                <span className="ml-2 text-sm text-ink/75">
                  {Math.ceil(d.size / 1024)} KB · {d.uploaded_by}, {dateTime(d.uploaded_at)}
                </span>
              </span>
              <span className="flex gap-1">
                <a
                  href={adminApi.documentUrl(m.id, d.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 font-semibold text-orange-text underline underline-offset-4"
                >
                  <FileText aria-hidden="true" className="size-4" /> View<span className="sr-only"> {d.filename}</span>
                </a>
                <button
                  type="button"
                  onClick={() => setDeleting(d)}
                  className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
                >
                  <Trash2 aria-hidden="true" className="size-4" /> Delete<span className="sr-only"> {d.filename}</span>
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={upload} noValidate className="flex flex-col gap-3 rounded-2xl bg-warm-white p-4 sm:flex-row sm:flex-wrap sm:items-end">
        <Select label="Kind" options={KINDS} value={kind} onChange={(e) => setKind(e.target.value as DocumentKind)} />
        <Field
          label="File (PDF, JPEG, PNG or WebP)"
          type="file"
          accept="application/pdf,image/jpeg,image/png,image/webp"
          className="[&_input]:pt-2.5"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <Button type="submit" className="h-12 rounded-full px-6 text-lg font-bold">
          Upload document
        </Button>
      </form>
      <SaveStatus status={status} />
      <Dialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete this document?"
        description={`${deleting?.filename} is deleted for good. The deletion is written to the audit log.`}
      >
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            className="h-11 rounded-full px-5 text-base font-bold"
            onClick={async () => {
              const d = deleting!;
              setDeleting(null);
              try {
                await adminApi.deleteDocument(m.id, d.id);
                set(docs.filter((x) => x.id !== d.id));
                setStatus({ kind: "saved", text: `${d.filename} deleted.` });
              } catch (err) {
                setStatus({ kind: "error", text: errorMessage(err) });
              }
            }}
          >
            Delete document
          </Button>
          <Button type="button" variant="outline" className="h-11 rounded-full px-5 text-base" onClick={() => setDeleting(null)}>
            Cancel
          </Button>
        </div>
      </Dialog>
    </Section>
  );
}
