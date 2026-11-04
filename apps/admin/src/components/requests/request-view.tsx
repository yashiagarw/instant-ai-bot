"use client";

import Link from "next/link";
import { useCallback, useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { ArrowLeft, Eye, Phone, TriangleAlert } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { TextArea } from "@/components/form";
import { type MapPoint, MapView } from "@/components/map-view";
import { CompleteJob } from "@/components/requests/complete-job";
import { SafetyBadge } from "@/components/requests/queue-view";
import { useMe } from "@/components/staff-shell";
import {
  adminApi,
  errorMessage,
  type Mechanic,
  type NotificationRow,
  type RequestDetail,
  type RequestEvent,
  type RequestStatus,
  type Suggestions,
} from "@/lib/api";
import { dateTime } from "@/lib/format";
import {
  age,
  channelLabel,
  MOVE_LABELS,
  needsNote,
  notificationOutcome,
  plainMoves,
  precisionNote,
  rupees,
  statusLabel,
  templateLabel,
} from "@/lib/ops";
import { useLoad } from "@/lib/use-load";

export function RequestView({ id }: { id: string }) {
  const { me } = useMe();
  const canUpdate = me.permissions.includes("requests.update");
  const { state, reload, set } = useLoad(useCallback((s: AbortSignal) => adminApi.request(id, s), [id]));
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");

  const act = useCallback(
    async (fn: () => Promise<RequestDetail>, done: string) => {
      setActionError("");
      setNotice("");
      try {
        set(await fn());
        setNotice(done);
        return true;
      } catch (e) {
        setActionError(errorMessage(e));
        return false;
      }
    },
    [set],
  );

  if (state.kind === "loading") return <p role="status">Loading the request…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const r = state.data;

  return (
    <div className="flex flex-col gap-6">
      <Link href="/requests" className="inline-flex min-h-11 items-center gap-2 self-start font-semibold text-orange-text underline underline-offset-4">
        <ArrowLeft aria-hidden="true" className="size-4" /> Request queue
      </Link>
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-black tracking-tight text-ink sm:text-4xl">{r.reference}</h1>
          <SafetyBadge level={r.safety_level} urgent={r.urgent} />
        </div>
        <p className="text-ink/80">
          <span className="font-bold text-ink" data-testid="request-status">
            {statusLabel(r.status)}
          </span>
          {" · "}received {dateTime(r.created_at)} ({age(r.age_minutes)} ago)
        </p>
      </header>
      {r.safety_level === "high" && (
        <p role="note" className="flex items-start gap-2 rounded-2xl bg-danger p-4 font-bold text-white">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
          Safety-critical: the diagnosis told the customer to stop driving. Call them first and send help or a tow.
        </p>
      )}
      <p aria-live="polite" className="font-semibold text-success" data-testid="request-notice">
        {notice}
      </p>
      {actionError && <ErrorBox message={actionError} />}

      <Owner request={r} canUpdate={canUpdate} act={act} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Customer request={r} />
        <Diagnosis request={r} />
      </div>
      <Workflow request={r} canUpdate={canUpdate} act={act} />
      {r.status === "in_progress" && canUpdate && (
        <CompleteJob
          request={r}
          onDone={(d) => {
            set(d);
            setNotice("Job completed. The confirmed fault is saved.");
          }}
        />
      )}
      {r.outcome && <OutcomeCard request={r} />}
      <div className="grid gap-6 lg:grid-cols-2">
        <Notes request={r} canUpdate={canUpdate} act={act} />
        <Timeline events={r.events} names={Object.fromEntries(r.assignments.map((a) => [a.mechanic_id, a.mechanic]))} />
      </div>
      <Notifications rows={r.notifications ?? []} />
    </div>
  );
}

/** What was sent about this request, to whom (masked) and how it went. Read-only. */
function Notifications({ rows }: { rows: NotificationRow[] }) {
  return (
    <Card title="Notifications">
      {rows.length === 0 ? (
        <p className="text-ink/75">Nothing sent about this request yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm" data-testid="notifications">
            <thead className="text-ink/70">
              <tr>
                <th scope="col" className="py-2 pr-3 font-semibold">When</th>
                <th scope="col" className="py-2 pr-3 font-semibold">Message</th>
                <th scope="col" className="py-2 pr-3 font-semibold">To</th>
                <th scope="col" className="py-2 pr-3 font-semibold">Channel</th>
                <th scope="col" className="py-2 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((n) => (
                <tr key={n.id} className="border-t border-border align-top">
                  <td className="py-2 pr-3 whitespace-nowrap text-ink/80">{dateTime(n.created_at)}</td>
                  <td className="py-2 pr-3 text-ink">
                    {templateLabel(n.template)}
                    {n.language === "hi" && <span className="text-ink/70"> (Hindi)</span>}
                  </td>
                  <td className="py-2 pr-3 text-ink">
                    {n.recipient} <span className="text-ink/70 tabular-nums">{n.to}</span>
                  </td>
                  <td className="py-2 pr-3 text-ink">
                    {channelLabel(n.channel)}
                    {n.previous_id !== null && <span className="text-ink/70"> (fallback)</span>}
                  </td>
                  <td
                    className={cn(
                      "py-2 font-semibold",
                      n.status === "failed" || n.status === "skipped" ? "text-orange-text" : "text-ink",
                    )}
                  >
                    {notificationOutcome(n)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

type Act = (fn: () => Promise<RequestDetail>, done: string) => Promise<boolean>;

function Card({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={cn("flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:p-6", className)}>
      <h2 id={id} className="text-xl font-black text-ink">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5 sm:grid-cols-[10rem_1fr]">
      <dt className="font-semibold text-ink/75">{label}</dt>
      <dd className="text-ink">{children || "–"}</dd>
    </div>
  );
}

// ---------------------------------------------------------------- owner and customer

function Owner({ request: r, canUpdate, act }: { request: RequestDetail; canUpdate: boolean; act: Act }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-warm-white p-4">
      <p className="text-ink">
        <span className="font-semibold">Owner: </span>
        {r.agent ?? "nobody yet"}
        {r.phone_revealable && " (you)"}
      </p>
      {canUpdate && !r.phone_revealable && r.allowed.length > 0 && (
        <Button type="button" className="h-11 rounded-full px-5 text-base font-bold" onClick={() => void act(() => adminApi.takeRequest(r.id), "You own this request now.")}>
          {r.agent ? "Take it over" : "Take this request"}
        </Button>
      )}
    </div>
  );
}

function Customer({ request: r }: { request: RequestDetail }) {
  const [phone, setPhone] = useState<string | null>(null);
  const [error, setError] = useState("");
  return (
    <Card title="Customer">
      <dl className="flex flex-col gap-2">
        <Row label="Name">{r.name}</Row>
        <Row label="Phone">
          <span className="flex flex-wrap items-center gap-2">
            {phone ? (
              <a href={`tel:${phone}`} className="inline-flex items-center gap-1 font-bold text-orange-text underline underline-offset-4">
                <Phone aria-hidden="true" className="size-4" /> {phone}
              </a>
            ) : (
              <span data-testid="masked-phone">{r.phone}</span>
            )}
            {!phone && r.phone_revealable && (
              <button
                type="button"
                onClick={async () => {
                  setError("");
                  try {
                    setPhone((await adminApi.revealRequestPhone(r.id)).phone);
                  } catch (e) {
                    setError(errorMessage(e));
                  }
                }}
                className="inline-flex min-h-11 items-center gap-1 rounded-full border border-border px-3 text-sm font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
              >
                <Eye aria-hidden="true" className="size-4" /> Show number
              </button>
            )}
          </span>
          {phone && <span className="block text-sm text-ink/75">This was written to the audit log.</span>}
          {!r.phone_revealable && <span className="block text-sm text-ink/75">Only the agent who owns this request can see the full number.</span>}
          {error && (
            <span role="alert" className="block text-sm font-semibold text-orange-text">
              {error}
            </span>
          )}
        </Row>
        <Row label="Address">{r.address}</Row>
        <Row label="Area">
          {r.area} {r.pincode}
        </Row>
        <Row label="Preferred time">{r.preferred_time}</Row>
        <Row label="Service">{r.service_type.replace(/_/g, " ")}</Row>
        <Row label="Customer's notes">{r.notes_from_customer}</Row>
      </dl>
    </Card>
  );
}

function Diagnosis({ request: r }: { request: RequestDetail }) {
  return (
    <Card title="Car and diagnosis">
      <dl className="flex flex-col gap-2">
        <Row label="Car">{r.vehicle}</Row>
        <Row label="Category">{r.category ?? r.category_code}</Row>
        <Row label="Problem">{r.problem_summary}</Row>
      </dl>
      {r.causes.length > 0 ? (
        <div className="flex flex-col gap-1">
          <h3 className="font-bold text-ink">AI&apos;s likely causes</h3>
          <ol className="flex flex-col gap-1">
            {r.causes.map((c) => (
              <li key={c.fault_key} className="flex flex-wrap gap-x-2">
                <span className="font-semibold">
                  {c.rank}. {c.name ?? c.fault_key}
                </span>
                <span className="text-ink/75">
                  {c.fault_key} · {c.confidence} confidence
                </span>
              </li>
            ))}
          </ol>
        </div>
      ) : (
        <p className="text-ink/80">No diagnosis is linked to this request.</p>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- workflow: status, offers, the mechanic's answer

function Workflow({ request: r, canUpdate, act }: { request: RequestDetail; canUpdate: boolean; act: Act }) {
  const { me } = useMe();
  const [noteFor, setNoteFor] = useState<RequestStatus | null>(null);
  const moves = canUpdate ? plainMoves(r.allowed) : [];
  const open = r.assignments.find((a) => a.status === "offered" || a.status === "accepted");
  const suggestions = useLoad(
    useCallback((s: AbortSignal) => (r.status === "triaged" ? adminApi.suggestions(r.id, s) : Promise.resolve(null)), [r.id, r.status]),
  );
  const mechanics = useLoad(
    useCallback(
      (s: AbortSignal) => (me.permissions.includes("mechanics.read") ? adminApi.mechanics(false, s) : Promise.resolve([] as Mechanic[])),
      [me.permissions],
    ),
  );
  const sug = suggestions.state.kind === "ready" ? suggestions.state.data : null;

  return (
    <Card title="Mechanic">
      <RequestMap request={r} suggestions={sug} mechanics={mechanics.state.kind === "ready" ? mechanics.state.data : []} />
      {open && (
        <div className="flex flex-col gap-2 rounded-2xl bg-warm-white p-4" data-testid="open-assignment">
          <p className="text-ink">
            <span className="font-bold">{open.mechanic}</span>{" "}
            {open.status === "offered" ? `was offered the job by ${open.offered_by}, ${dateTime(open.offered_at)}.` : "accepted the job."}
          </p>
          {open.status === "offered" && canUpdate && (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                className="h-11 rounded-full px-5 text-base font-bold"
                onClick={() => void act(() => adminApi.mechanicAnswer(r.id, true), `${open.mechanic} accepted the job.`)}
              >
                Mechanic accepted
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-11 rounded-full px-5 text-base"
                onClick={() => void act(() => adminApi.mechanicAnswer(r.id, false), `${open.mechanic} declined. Offer it to someone else.`)}
              >
                Mechanic declined
              </Button>
            </div>
          )}
        </div>
      )}
      {r.status === "triaged" && (
        <SuggestionList request={r} state={suggestions.state} reload={suggestions.reload} canUpdate={canUpdate} act={act} />
      )}
      {r.status === "submitted" && canUpdate && <p className="text-ink/80">Triage the request (call the customer) before offering it to a mechanic.</p>}
      {moves.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="font-bold text-ink">Change the status</h3>
          <div className="flex flex-wrap gap-2">
            {moves.map((s) => (
              <Button
                key={s}
                type="button"
                variant={needsNote(s) ? "outline" : "default"}
                className={cn("h-11 rounded-full px-5 text-base font-bold", needsNote(s) && "font-semibold")}
                onClick={() => (needsNote(s) ? setNoteFor(s) : void act(() => adminApi.setRequestStatus(r.id, s), `Now: ${statusLabel(s)}.`))}
              >
                {MOVE_LABELS[s]}
              </Button>
            ))}
          </div>
        </div>
      )}
      {r.assignments.length > 0 && (
        <details className="rounded-2xl border border-border p-3">
          <summary className="min-h-11 cursor-pointer content-center font-semibold">Offers so far ({r.assignments.length})</summary>
          <ul className="mt-2 flex flex-col gap-2">
            {r.assignments.map((a) => (
              <li key={a.id} className="text-sm">
                <span className="font-semibold">{a.mechanic}</span>: {a.status}, offered {dateTime(a.offered_at)} by {a.offered_by}
                {a.match.suggested === false && " (not a suggestion)"}
                {a.note && <span className="block text-ink/75">{a.note}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
      <NoteDialog
        status={noteFor}
        onClose={() => setNoteFor(null)}
        onSubmit={async (note) => {
          const s = noteFor!;
          if (await act(() => adminApi.setRequestStatus(r.id, s, note), `Now: ${statusLabel(s)}.`)) setNoteFor(null);
        }}
      />
    </Card>
  );
}

function RequestMap({ request: r, suggestions, mechanics }: { request: RequestDetail; suggestions: Suggestions | null; mechanics: Mechanic[] }) {
  const points = useMemo<MapPoint[]>(() => {
    const out: MapPoint[] = [];
    if (r.point) out.push({ id: "request", lat: r.point.lat, lon: r.point.lon, label: `${r.reference}: ${r.area} ${r.pincode}`, tone: "request", rough: r.point.precision !== "pincode" });
    for (const s of suggestions?.suggestions ?? []) {
      const m = mechanics.find((x) => x.id === s.mechanic_id);
      if (m?.base_point) out.push({ id: `m${m.id}`, lat: m.base_point[0], lon: m.base_point[1], label: m.name, tone: "mechanic", rough: m.base_precision !== "pincode" });
    }
    return out;
  }, [r, suggestions, mechanics]);
  const note = precisionNote(r.point?.precision);
  return (
    <div className="flex flex-col gap-2">
      {r.point ? (
        <>
          <MapView label={`Where ${r.reference} is`} points={points} />
          <p className="text-sm text-ink/80">
            Pincode {r.pincode} centre (approximate)
            {note && (
              <span className="ml-1 rounded-full bg-amber-bg px-2 py-0.5 font-bold text-amber-text" data-testid="rough-location">
                {note}
              </span>
            )}
            {points.length > 1 && " · orange: suggested mechanics' bases"}
          </p>
        </>
      ) : (
        <p className="text-ink/80">No map point for pincode {r.pincode || "(none given)"}: it is outside our Delhi NCR zones.</p>
      )}
    </div>
  );
}

function SuggestionList({
  request: r,
  state,
  reload,
  canUpdate,
  act,
}: {
  request: RequestDetail;
  state: ReturnType<typeof useLoad<Suggestions | null>>["state"];
  reload: () => void;
  canUpdate: boolean;
  act: Act;
}) {
  const [anyway, setAnyway] = useState<{ id: number; name: string; reasons: string[] } | null>(null);
  if (state.kind === "loading") return <p role="status">Finding mechanics…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const s = state.data;
  if (!s) return null;
  return (
    <div className="flex flex-col gap-3">
      <h3 className="font-bold text-ink">Suggested mechanics</h3>
      {s.notes.map((n) => (
        <p key={n} className="text-sm font-semibold text-amber-text">
          {n}
        </p>
      ))}
      {s.suggestions.length === 0 && <p className="text-ink/80">Nobody fits right now. See who was left out and why below.</p>}
      <ol aria-label="Suggested mechanics" className="flex flex-col gap-3">
        {s.suggestions.map((m, i) => (
          <li key={m.mechanic_id} className="flex flex-col gap-2 rounded-2xl border border-border p-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-col gap-1">
              <p className="font-bold text-ink">
                {i + 1}. {m.name}
                <span className="ml-2 font-semibold text-ink/75">score {m.score.toFixed(2)}</span>
              </p>
              <ul className="list-disc pl-5 text-sm text-ink/80">
                {m.reasons.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
            {canUpdate && (
              <Button
                type="button"
                className="h-11 shrink-0 rounded-full px-5 text-base font-bold"
                onClick={() => void act(() => adminApi.offer(r.id, m.mechanic_id), `Offered to ${m.name}. Record their answer when they reply.`)}
              >
                Offer job<span className="sr-only"> to {m.name}</span>
              </Button>
            )}
          </li>
        ))}
      </ol>
      {s.excluded.length > 0 && (
        <details className="rounded-2xl border border-border p-3">
          <summary className="min-h-11 cursor-pointer content-center font-semibold">Left out ({s.excluded.length})</summary>
          <ul className="mt-2 flex flex-col gap-2">
            {s.excluded.map((x) => (
              <li key={x.mechanic_id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span>
                  <span className="font-semibold">{x.name}</span>: {x.reasons.join("; ")}
                </span>
                {canUpdate && (
                  <button
                    type="button"
                    onClick={() => setAnyway({ id: x.mechanic_id, name: x.name, reasons: x.reasons })}
                    className="min-h-11 rounded-full border border-border px-3 font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
                  >
                    Offer anyway<span className="sr-only"> to {x.name}</span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      <Dialog
        open={anyway !== null}
        onOpenChange={(o) => !o && setAnyway(null)}
        title={`Offer to ${anyway?.name ?? ""} anyway?`}
        description={`Not a suggestion: ${anyway?.reasons.join("; ")}. Say why you're offering anyway.`}
      >
        <NoteForm
          label="Why"
          submitLabel="Offer job"
          onSubmit={async (note) => {
            const m = anyway!;
            if (await act(() => adminApi.offer(r.id, m.id, note), `Offered to ${m.name}. Record their answer when they reply.`)) setAnyway(null);
          }}
        />
      </Dialog>
    </div>
  );
}

function NoteDialog({ status, onClose, onSubmit }: { status: RequestStatus | null; onClose: () => void; onSubmit: (note: string) => Promise<void> }) {
  return (
    <Dialog
      open={status !== null}
      onOpenChange={(o) => !o && onClose()}
      title={status === "cancelled" ? "Cancel this request?" : "Escalate this request?"}
      description={status === "cancelled" ? "The customer sees it as cancelled. Say why." : "A senior team member takes a look. Say why."}
    >
      <NoteForm label="Why" submitLabel={status ? (MOVE_LABELS[status] ?? "Save") : "Save"} onSubmit={onSubmit} />
    </Dialog>
  );
}

function NoteForm({ label, submitLabel, onSubmit }: { label: string; submitLabel: string; onSubmit: (note: string) => Promise<void> }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      noValidate
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!note.trim()) return setError("Write a short note.");
        setError("");
        setBusy(true);
        await onSubmit(note.trim());
        setBusy(false);
      }}
    >
      <TextArea label={label} rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} error={error ? { message: error } : undefined} />
      <Button type="submit" disabled={busy} className="h-12 self-start rounded-full px-6 text-lg font-bold">
        {submitLabel}
      </Button>
    </form>
  );
}

// ---------------------------------------------------------------- outcome, notes, timeline

function OutcomeCard({ request: r }: { request: RequestDetail }) {
  const o = r.outcome!;
  const ai = o.ai_top1 === null ? "No diagnosis to compare" : o.ai_top1 ? "The AI's top cause" : o.ai_top3 ? "In the AI's top 3" : "Not in the AI's top 3";
  return (
    <Card title="Outcome">
      <dl className="flex flex-col gap-2">
        <Row label="Confirmed fault">{o.confirmed_fault_key ? `${o.confirmed_fault ?? ""} (${o.confirmed_fault_key})` : `Other: ${o.other_text}`}</Row>
        <Row label="AI">{ai}</Row>
        <Row label="Parts used">
          {o.parts_used.map((p) => `${p.quantity} × ${p.name}${p.price_inr !== null ? ` (${rupees(p.price_inr)})` : ""}`).join(", ")}
        </Row>
        <Row label="Final cost">{rupees(o.final_cost_inr)}</Row>
        <Row label="Mechanic's notes">{o.mechanic_notes}</Row>
        <Row label="Recorded">
          {o.recorded_by}, {dateTime(o.recorded_at)}
        </Row>
      </dl>
    </Card>
  );
}

function Notes({ request: r, canUpdate, act }: { request: RequestDetail; canUpdate: boolean; act: Act }) {
  const [text, setText] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    if (await act(() => adminApi.addRequestNote(r.id, text.trim()), "Note added.")) setText("");
  }
  return (
    <Card title="Internal notes">
      <p className="text-sm text-ink/75">Staff only: never shown to the customer.</p>
      <ul aria-label="Internal notes" className="flex flex-col gap-2">
        {r.internal_notes.length === 0 && <li className="text-ink/80">No notes yet.</li>}
        {r.internal_notes.map((n) => (
          <li key={n.id} className="rounded-2xl bg-warm-white p-3">
            <p className="whitespace-pre-line text-ink">{n.text}</p>
            <p className="text-sm text-ink/75">
              {n.author}, {dateTime(n.created_at)}
            </p>
          </li>
        ))}
      </ul>
      {canUpdate && (
        <form onSubmit={submit} className="flex flex-col gap-2">
          <TextArea label="Add a note" rows={2} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} />
          <Button type="submit" variant="outline" className="h-11 self-start rounded-full px-5 text-base font-bold">
            Add note
          </Button>
        </form>
      )}
    </Card>
  );
}

function eventText(e: RequestEvent, names: Record<number, string>): string {
  const id = (e.data as { mechanic_id?: number }).mechanic_id;
  const mech = id === undefined ? "the mechanic" : (names[id] ?? `mechanic #${id}`);
  switch (e.kind) {
    case "status":
      return e.from_status ? `${statusLabel(e.from_status)} → ${statusLabel(e.to_status)}` : statusLabel(e.to_status);
    case "offer":
      return `Offered to ${mech}`;
    case "response":
      return (e.data as { accepted?: boolean }).accepted ? `${mech} accepted` : `${mech} declined`;
    case "agent":
      return `Owner: ${String((e.data as { agent?: string }).agent ?? "")}`;
    case "outcome":
      return `Confirmed fault: ${String((e.data as { confirmed_fault_key?: string }).confirmed_fault_key ?? "")}`;
  }
}

function Timeline({ events, names }: { events: RequestEvent[]; names: Record<number, string> }) {
  return (
    <Card title="Timeline">
      <ol aria-label="Timeline" className="flex flex-col gap-3 border-l-2 border-border pl-4">
        {[...events].reverse().map((e) => (
          <li key={e.id} className="flex flex-col">
            <span className="font-semibold text-ink">{eventText(e, names)}</span>
            <span className="text-sm text-ink/75">
              {dateTime(e.at)} · {e.actor}
            </span>
            {e.note && <span className="text-sm text-ink/80">{e.note}</span>}
          </li>
        ))}
      </ol>
    </Card>
  );
}
