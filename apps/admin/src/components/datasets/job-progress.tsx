"use client";

import { useEffect, useRef, useState } from "react";
import { CircleCheck, CircleAlert, Loader } from "lucide-react";

import { Button } from "@im/ui/button";
import { adminApi, type DatasetJob, errorMessage } from "@/lib/api";
import { isActive, JOB_KIND, waitingSeconds } from "@/lib/datasets";

const POLL_MS = 1500;
const WORKER_HINT_AFTER_S = 10;

/** Follows a job until it finishes (polling), then calls onDone once with its final state. */
export function useJob(initial: DatasetJob | null, onDone: (job: DatasetJob) => void) {
  const [job, setJob] = useState<DatasetJob | null>(initial);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  }, [onDone]);

  const [tracked, setTracked] = useState(initial);
  if (initial !== tracked) {
    setTracked(initial);
    setJob(initial);
  }

  const id = job?.id;
  const active = isActive(job);
  useEffect(() => {
    if (!id || !active) return;
    const ctrl = new AbortController();
    const timer = setInterval(() => {
      adminApi
        .datasetJob(id, ctrl.signal)
        .then((j) => {
          setJob(j);
          if (!isActive(j)) done.current(j);
        })
        .catch(() => undefined); // a missed poll is retried on the next tick
    }, POLL_MS);
    return () => {
      clearInterval(timer);
      ctrl.abort();
    };
  }, [id, active]);
  return [job, setJob] as const;
}

/** A job's progress bar, step and log; while queued for a while, how to start the worker. */
export function JobProgress({ job, canCancel, onCancelled }: { job: DatasetJob; canCancel?: boolean; onCancelled?: () => void }) {
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (job.status !== "queued") return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [job.status]);

  const label = JOB_KIND[job.kind];
  const waiting = waitingSeconds(job, now);
  return (
    <section
      aria-label={`${label}: job ${job.id}`}
      data-testid="job-progress"
      className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-bold text-ink">
          {isActive(job) ? (
            <Loader aria-hidden="true" className="size-5 animate-spin text-orange-text motion-reduce:animate-none" />
          ) : job.status === "succeeded" ? (
            <CircleCheck aria-hidden="true" className="size-5 text-orange-text" />
          ) : (
            <CircleAlert aria-hidden="true" className="size-5 text-orange-text" />
          )}
          {label}
        </h2>
        <span className="text-sm text-ink/70">
          Job {job.id} · started by {job.created_by}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={job.progress}
        aria-valuetext={`${job.progress}%: ${job.step}`}
        className="h-3 overflow-hidden rounded-full bg-warm-white"
      >
        <div className="h-full rounded-full bg-brand transition-[width]" style={{ width: `${job.progress}%` }} />
      </div>
      <p className="text-ink" aria-live="polite">
        <span className="font-bold">{job.status === "queued" ? "Waiting for the worker" : job.status === "running" ? `${job.progress}%` : job.status === "succeeded" ? "Done" : "Failed"}</span>
        {job.status === "running" && <> · {job.step}</>}
      </p>
      {job.error && (
        <p role="alert" className="font-semibold text-orange-text">
          {job.error}
        </p>
      )}
      {job.status === "queued" && waiting >= WORKER_HINT_AFTER_S && (
        <p className="rounded-2xl bg-warm-white p-3 text-sm text-ink">
          Still waiting after {waiting} s. Is the worker running? Start it with{" "}
          <code className="font-mono font-bold">cd backend &amp;&amp; uv run arq app.datasets.worker.WorkerSettings</code> (Redis:{" "}
          <code className="font-mono font-bold">docker compose up -d redis</code>).
        </p>
      )}
      {canCancel && job.status === "queued" && (
        <div>
          <Button
            type="button"
            variant="outline"
            className="h-11 rounded-full px-5 text-base"
            onClick={() =>
              adminApi
                .cancelJob(job.id)
                .then(() => onCancelled?.())
                .catch((e) => setError(errorMessage(e)))
            }
          >
            Cancel job
          </Button>
          {error && <p className="mt-2 font-semibold text-orange-text">{error}</p>}
        </div>
      )}
      {job.log.length > 0 && (
        <details>
          <summary className="min-h-11 cursor-pointer py-2 font-semibold text-orange-text">Steps so far</summary>
          <ol className="flex flex-col gap-1 text-sm text-ink/80">
            {job.log.map((l, i) => (
              <li key={i}>
                <time dateTime={l.at}>{new Date(l.at).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })}</time> · {l.step}
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
