"use client";

import Link from "next/link";
import { useCallback, useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { ArrowLeft, Star } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { Select, TextArea } from "@/components/form";
import { useMe } from "@/components/staff-shell";
import { adminApi, errorMessage, type GoldenInput, type Replay } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

const STEP_LABELS: Record<string, string> = {
  session_started: "Start",
  free_text: "Customer typed",
  question_asked: "Question",
  answer_given: "Answer",
  answer_undone: "Undo",
  question_withdrawn: "Set aside",
  message_undone: "Undo",
  safety_alert: "Safety alert",
  result_computed: "Result",
};

/** One diagnosis session, read-only: every step with its time (India), what still counted, the result, feedback and
 * the confirmed fault if a mechanic completed a job for it. */
export function ReplayView({ id }: { id: string }) {
  const { me } = useMe();
  const { state, reload, set } = useLoad(useCallback((s: AbortSignal) => adminApi.replay(id, s), [id]));
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState("");

  if (state.kind === "loading") return <p role="status">Loading the session…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const r = state.data;
  return (
    <div className="flex flex-col gap-6">
      <Link href="/quality" className="inline-flex min-h-11 items-center gap-2 self-start font-semibold text-orange-text underline underline-offset-4">
        <ArrowLeft aria-hidden="true" className="size-4" /> Quality
      </Link>
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-black tracking-tight text-ink sm:text-4xl">Session replay</h1>
        <p className="text-ink/80">
          {r.vehicle} · started {dateTime(r.created_at)} · {r.status.replace(/_/g, " ")} · {r.questions_answered} question
          {r.questions_answered === 1 ? "" : "s"} answered
        </p>
        <p className="text-sm text-ink/75">
          Read-only. Phone numbers, emails and number plates are hidden. Engine {r.engine_version}
          {r.dataset_version_id ? `, dataset version ${r.dataset_version_id}` : ""}
          {r.coverage_level ? `, coverage ${r.coverage_level.replace(/_/g, " ")}` : ""}.
        </p>
      </header>
      <p aria-live="polite" className="font-semibold text-success">
        {notice}
      </p>

      <Golden replay={r} canAdd={me.permissions.includes("quality.golden")} onAdd={() => setAdding(true)} />

      <Card title="Questions and answers">
        <ol aria-label="Session steps" className="flex flex-col gap-3 border-l-2 border-border pl-4">
          {r.steps.map((s) => (
            <li key={s.id} className={cn("flex flex-col", !s.counted && "opacity-70")} data-testid="replay-step">
              <span className="text-sm text-ink/75">
                <time dateTime={s.at}>{dateTime(s.at)}</time> · {STEP_LABELS[s.kind] ?? s.kind}
                {!s.counted && <span className="ml-1 font-semibold">(taken back: did not count)</span>}
              </span>
              <span className={cn("font-semibold", s.kind === "safety_alert" ? "text-danger" : "text-ink", !s.counted && "line-through")}>{s.text}</span>
              {s.detail && <span className="text-sm text-ink/80">{s.detail}</span>}
            </li>
          ))}
        </ol>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Result">
          {r.results.length === 0 ? (
            <p className="text-ink/80">No cause found (no match).</p>
          ) : (
            <ol className="flex flex-col gap-1">
              {r.results.map((x) => (
                <li key={x.rank}>
                  <span className="font-semibold">
                    {x.rank}. {x.name ?? x.fault_key}
                  </span>{" "}
                  <span className="text-ink/75">
                    {x.fault_key} · {x.confidence} confidence
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Card>
        <Card title="Feedback and outcome">
          {r.feedback.length === 0 && <p className="text-ink/80">No feedback.</p>}
          {r.feedback.map((f, i) => (
            <p key={i} className="text-ink">
              <span className="font-semibold">{f.helpful === null ? "No answer" : f.helpful ? "Helpful" : "Not helpful"}</span> ({f.source}, {dateTime(f.at)})
              {f.comment && <span className="block text-ink/80">&ldquo;{f.comment}&rdquo;</span>}
            </p>
          ))}
          {r.request ? (
            <p className="text-ink" data-testid="replay-request">
              Request {r.request.reference}:{" "}
              {r.request.completed
                ? `mechanic confirmed ${r.request.confirmed_fault_key ? `${r.request.confirmed_fault ?? ""} (${r.request.confirmed_fault_key})` : `other: ${r.request.other_text}`}`
                : r.request.status.replace(/_/g, " ")}
            </p>
          ) : (
            <p className="text-ink/80">No mechanic request.</p>
          )}
        </Card>
      </div>
      {adding && (
        <GoldenDialog
          replay={r}
          onClose={() => setAdding(false)}
          onDone={(g) => {
            set({ ...r, golden: g });
            setAdding(false);
            setNotice(`Added to the golden set as ${g.case_id}.`);
          }}
        />
      )}
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:p-6">
      <h2 id={id} className="text-xl font-black text-ink">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Golden({ replay: r, canAdd, onAdd }: { replay: Replay; canAdd: boolean; onAdd: () => void }) {
  if (r.golden) {
    return (
      <p className="rounded-2xl bg-success-bg p-4 font-semibold text-success" data-testid="in-golden">
        In the golden set as {r.golden.case_id} (expected {r.golden.expected.join(", ") || "an alert"}), added by {r.golden.added_by}, {dateTime(r.golden.at)}.
      </p>
    );
  }
  if (!canAdd) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-warm-white p-4">
      <p className="text-ink">Is the right answer for this session known? Add it to the test cases the app is checked against.</p>
      <Button type="button" className="h-12 rounded-full px-6 text-lg font-bold" onClick={onAdd}>
        <Star aria-hidden="true" className="size-5" /> Add to golden set
      </Button>
    </div>
  );
}

type GoldenResult = NonNullable<Replay["golden"]>;

function GoldenDialog({ replay: r, onClose, onDone }: { replay: Replay; onClose: () => void; onDone: (g: GoldenResult) => void }) {
  const { state } = useLoad(useCallback((s: AbortSignal) => adminApi.qualityFaults(s), []));
  const mechanic = r.request?.completed ? r.request.confirmed_fault_key : null;
  const [fault, setFault] = useState(mechanic ?? "");
  const [alert, setAlert] = useState("");
  const [confirmedBy, setConfirmedBy] = useState<GoldenInput["confirmed_by"]>(mechanic ? "mechanic" : "staff");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // The session's own causes first, then every fault of the live version.
  const options = useMemo(() => {
    const all = state.kind === "ready" ? state.data : [];
    const top = r.results.map((x) => ({ value: x.fault_key, label: `Result #${x.rank}: ${x.name ?? x.fault_key} (${x.fault_key})` }));
    const rest = all.filter((f) => !r.results.some((x) => x.fault_key === f.fault_key)).map((f) => ({ value: f.fault_key, label: `${f.name} (${f.fault_key})` }));
    return [{ value: "", label: "No fault (alert only)" }, ...top, ...rest];
  }, [state, r.results]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!fault && !alert) return setError("Choose the right fault, or the safety alert this case should show.");
    setBusy(true);
    setError("");
    try {
      const out = await adminApi.addToGolden(r.id, {
        expected: fault ? [fault] : [],
        expected_alert: (alert || null) as GoldenInput["expected_alert"],
        confirmed_by: confirmedBy,
        note: note.trim(),
      });
      onDone({ case_id: out.case_id, added_by: out.added_by, at: new Date().toISOString(), expected: fault ? [fault] : [], file_path: out.file_path });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Add to golden set"
      description="The session becomes a real test case. Names, phone numbers and addresses are removed; only the pincode is kept."
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <Select label="Right fault" value={fault} onChange={(e) => setFault(e.target.value)} options={options} />
        {mechanic && fault === mechanic && <p className="text-sm text-ink/80">This is the fault the mechanic confirmed.</p>}
        <Select
          label="Safety alert it should show"
          value={alert}
          onChange={(e) => setAlert(e.target.value)}
          options={[
            { value: "", label: "Not checked" },
            { value: "none", label: "No alert" },
            { value: "low", label: "Low or higher" },
            { value: "medium", label: "Medium or higher" },
            { value: "high", label: "High" },
          ]}
        />
        <Select
          label="Who confirmed it"
          value={confirmedBy}
          onChange={(e) => setConfirmedBy(e.target.value as GoldenInput["confirmed_by"])}
          options={[
            ...(r.request?.completed ? [{ value: "mechanic", label: "The mechanic, on the completed job" }] : []),
            { value: "staff", label: "Me, from this replay" },
          ]}
        />
        <TextArea label="Note (optional)" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        {error && <ErrorBox message={error} />}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={busy} className="h-12 rounded-full px-6 text-lg font-bold">
            Add case
          </Button>
          <Button type="button" variant="outline" className="h-12 rounded-full px-5 text-base" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
