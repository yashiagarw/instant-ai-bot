"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";
import { CheckCircle2, LoaderCircle, MapPin, Phone, ShieldAlert } from "lucide-react";

import { useStatusName, useT } from "@/components/m/i18n";
import { PRIMARY, SECONDARY } from "@/components/m/shell";
import { cn } from "@/lib/utils";
import { mechanicApi, MechanicApiError, type FaultChoice, type Job } from "@/lib/mechanic-api";

const ETA_CHOICES = [10, 20, 30, 45, 60];

export function JobView() {
  const t = useT();
  const status = useStatusName();
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fail = useCallback(
    (e: unknown) => {
      if (e instanceof MechanicApiError) {
        if (e.status === 0) return setError(t("offline"));
        if (e.message) return setError(e.message);
      }
      setError(t("error"));
    },
    [t],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    mechanicApi.job(jobId, ctrl.signal).then(setJob).catch((e) => !ctrl.signal.aborted && fail(e));
    return () => ctrl.abort();
  }, [jobId, fail]);

  async function run(fn: () => Promise<Job>, done?: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setJob(await fn());
      if (done) setNotice(done);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }

  async function call() {
    setBusy(true);
    setError(null);
    try {
      await mechanicApi.callCustomer(jobId);
      setNotice(t("calling"));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }

  if (!job) {
    return error ? (
      <p role="alert" className="text-lg font-bold text-danger">
        {error}
      </p>
    ) : (
      <p className="text-lg">{t("loading")}</p>
    );
  }
  const finished = job.status === "completed";
  return (
    <>
      <div>
        <p className="text-base font-bold text-ink/70">{t("job")}</p>
        <h1 className="text-3xl font-black tabular-nums">{job.reference}</h1>
        <p className="mt-1 inline-block rounded-full bg-ink px-3 py-1 text-lg font-bold text-white" data-testid="job-status">
          {status(job.status)}
        </p>
      </div>
      {job.safety_critical && (
        <p className="flex items-start gap-2 rounded-2xl bg-danger p-3 text-lg font-bold text-white">
          <ShieldAlert aria-hidden="true" className="mt-0.5 size-6 shrink-0" />
          {t("safety")}
        </p>
      )}
      <section className="flex flex-col gap-3 rounded-3xl border-2 border-ink/10 bg-white p-4" aria-label={t("address")}>
        <p className="text-base font-bold text-ink/70">{t("address")}</p>
        <p className="text-xl font-bold" data-testid="job-address">
          {job.address}
        </p>
        <a href={job.map_url} target="_blank" rel="noopener noreferrer" className={SECONDARY}>
          <MapPin aria-hidden="true" className="size-6" />
          {t("openMap")}
        </a>
        <p className="text-base font-bold text-ink/70">{t("customer")}</p>
        <p className="text-xl font-bold">
          {job.customer_name} · <span className="tabular-nums" data-testid="job-phone">{job.customer_phone}</span>
        </p>
        {job.can_call && (
          <button type="button" className={PRIMARY} onClick={call} disabled={busy}>
            <Phone aria-hidden="true" className="size-6" />
            {t("callCustomer")}
          </button>
        )}
        {job.notes && (
          <>
            <p className="text-base font-bold text-ink/70">{t("notes")}</p>
            <p className="text-lg">{job.notes}</p>
          </>
        )}
        <p className="text-base font-bold text-ink/70">{t("car")}</p>
        <p className="text-lg">{job.car}</p>
        <p className="text-base font-bold text-ink/70">{t("problem")}</p>
        <p className="text-lg">{job.problem}</p>
      </section>

      {notice && (
        <p role="status" className="rounded-2xl bg-success-bg p-3 text-lg font-bold text-success">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-2xl bg-white p-3 text-lg font-bold text-danger">
          {error}
        </p>
      )}

      {(job.status === "accepted" || job.status === "en_route") && (
        <Eta job={job} busy={busy} onPick={(n) => run(() => mechanicApi.setEta(jobId, n), t("etaSaved", { n }))} />
      )}
      {job.next_status === "en_route" && (
        <button type="button" className={PRIMARY} disabled={busy} onClick={() => run(() => mechanicApi.setStatus(jobId, { status: "en_route" }))}>
          {t("startTravel")}
        </button>
      )}
      {job.next_status === "arrived" && (
        <button type="button" className={PRIMARY} disabled={busy} onClick={() => run(() => mechanicApi.setStatus(jobId, { status: "arrived" }))}>
          {t("arrived")}
        </button>
      )}
      {job.next_status === "in_progress" && (
        <button type="button" className={PRIMARY} disabled={busy} onClick={() => run(() => mechanicApi.setStatus(jobId, { status: "in_progress" }))}>
          {t("startWork")}
        </button>
      )}
      {job.next_status === "completed" && <Finish jobId={jobId} onDone={setJob} />}
      {finished && (
        <p className="flex items-center gap-2 rounded-2xl bg-success-bg p-4 text-xl font-black text-success" role="status">
          <CheckCircle2 aria-hidden="true" className="size-7" />
          {t("done")}
        </p>
      )}
    </>
  );
}

function Eta({ job, busy, onPick }: { job: Job; busy: boolean; onPick: (n: number) => void }) {
  const t = useT();
  const id = useId();
  return (
    <fieldset className="flex flex-col gap-2 rounded-3xl border-2 border-ink/10 bg-white p-4" aria-describedby={`${id}-now`}>
      <legend className="text-xl font-black">{t("etaQuestion")}</legend>
      {job.eta_at && (
        <p id={`${id}-now`} className="text-base text-ink/80">
          {t("eta")}: {new Date(job.eta_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })}
        </p>
      )}
      <div className="grid grid-cols-3 gap-2">
        {ETA_CHOICES.map((n) => (
          <button
            key={n}
            type="button"
            disabled={busy}
            onClick={() => onPick(n)}
            className="min-h-14 rounded-2xl border-2 border-ink bg-white text-xl font-black outline-none focus-visible:ring-4 focus-visible:ring-ring"
          >
            {n} {t("minutes")}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

/** Completion: the fault actually found (searchable, Hindi names, AI's guesses first), or "other / not sure". */
function Finish({ jobId, onDone }: { jobId: number; onDone: (j: Job) => void }) {
  const t = useT();
  const id = useId();
  const [q, setQ] = useState("");
  const [choices, setChoices] = useState<FaultChoice[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [other, setOther] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    const timer = setTimeout(
      () =>
        mechanicApi
          .faults(jobId, q, ctrl.signal)
          .then(setChoices)
          .catch(() => undefined),
      q ? 300 : 0,
    );
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [jobId, q]);

  async function finish() {
    if (!picked || (picked === "other" && !other.trim())) return setError(t("pickFault"));
    setBusy(true);
    setError(null);
    try {
      onDone(
        await mechanicApi.setStatus(jobId, {
          status: "completed",
          confirmed_fault_key: picked,
          other_text: picked === "other" ? other.trim() : "",
          notes: notes.trim(),
        }),
      );
    } catch (e) {
      setError(e instanceof MechanicApiError && e.message ? e.message : t("error"));
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-3xl border-2 border-ink bg-white p-4" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className="text-2xl font-black">
        {t("whatFault")}
      </h2>
      <label className="flex flex-col gap-1 text-lg font-bold">
        {t("searchFault")}
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="min-h-14 rounded-2xl border-2 border-ink/30 px-4 text-xl outline-none focus-visible:ring-4 focus-visible:ring-ring"
        />
      </label>
      <div role="radiogroup" aria-label={t("whatFault")} className="flex max-h-[26rem] flex-col gap-2 overflow-y-auto" data-testid="fault-choices">
        {choices.map((c) => (
          <Choice key={c.fault_key} checked={picked === c.fault_key} onPick={() => setPicked(c.fault_key)}>
            <span className="text-lg font-bold">{c.name_hi ?? c.name}</span>
            {c.name_hi && <span className="text-base">{c.name}</span>}
            <span className="text-sm text-ink/70">
              {c.category}
              {c.ai_rank && ` · ${t("aiGuess")} #${c.ai_rank}`}
            </span>
          </Choice>
        ))}
        <Choice checked={picked === "other"} onPick={() => setPicked("other")}>
          <span className="text-lg font-bold">{t("other")}</span>
        </Choice>
      </div>
      {picked === "other" && (
        <label className="flex flex-col gap-1 text-lg font-bold">
          {t("otherNote")}
          <input
            value={other}
            maxLength={300}
            onChange={(e) => setOther(e.target.value)}
            className="min-h-14 rounded-2xl border-2 border-ink/30 px-4 text-xl outline-none focus-visible:ring-4 focus-visible:ring-ring"
          />
        </label>
      )}
      <label className="flex flex-col gap-1 text-lg font-bold">
        {t("workNotes")}
        <textarea
          value={notes}
          maxLength={1000}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="rounded-2xl border-2 border-ink/30 p-3 text-lg outline-none focus-visible:ring-4 focus-visible:ring-ring"
        />
      </label>
      {error && (
        <p role="alert" className="text-lg font-bold text-danger">
          {error}
        </p>
      )}
      <button type="button" className={PRIMARY} onClick={finish} disabled={busy}>
        {busy && <LoaderCircle aria-hidden="true" className="size-6 animate-spin motion-reduce:animate-none" />}
        {t("confirmFinish")}
      </button>
    </section>
  );
}

function Choice({ checked, onPick, children }: { checked: boolean; onPick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      onClick={onPick}
      className={cn(
        "flex min-h-14 flex-col items-start rounded-2xl border-2 p-3 text-left outline-none focus-visible:ring-4 focus-visible:ring-ring",
        checked ? "border-cta bg-amber-bg" : "border-ink/20 bg-white",
      )}
    >
      {children}
    </button>
  );
}
