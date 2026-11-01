"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Check, Circle, CircleDot, X } from "lucide-react";

import { PhotoGallery, photoAlerts, usePhotos } from "@/components/diagnose/photo-findings";
import { ErrorMessage } from "@/components/error-message";
import { SafetyBanner } from "@/components/safety-banner";
import { Skeleton } from "@/components/skeleton";
import { accountApi, type RequestDetail as RequestDetailType, type TimelineStep } from "@/lib/api";
import { indiaTime, shortDate } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

const ICON = { done: Check, current: CircleDot, upcoming: Circle, cancelled: X } as const;
const STATE_LABEL = { done: "Done", current: "Now", upcoming: "Next", cancelled: "Cancelled" } as const;
const SERVICE = { at_location: "Mechanic comes to the car", tow: "Tow", workshop: "Workshop visit" } as const;

function Timeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <ol className="flex flex-col" data-testid="timeline">
      {steps.map((s, i) => {
        const Icon = ICON[s.state];
        return (
          <li key={s.key} className="relative flex gap-3 pb-5 last:pb-0" aria-current={s.state === "current" ? "step" : undefined}>
            {i < steps.length - 1 && (
              <span aria-hidden="true" className="absolute top-8 left-[15px] h-[calc(100%-2rem)] w-0.5 bg-ink/15" />
            )}
            <span
              className={cn(
                "flex size-8 shrink-0 items-center justify-center rounded-full border-2",
                s.state === "done" && "border-success bg-success-bg text-success",
                s.state === "current" && "border-orange-text bg-warm-white text-orange-text",
                s.state === "upcoming" && "border-ink/20 bg-white text-ink/40",
                s.state === "cancelled" && "border-ink bg-ink text-white",
              )}
            >
              <Icon aria-hidden="true" className="size-4" />
            </span>
            <span className="flex flex-col pt-0.5">
              <span className={cn("font-bold", s.state === "upcoming" ? "text-ink/60" : "text-ink")}>{s.label}</span>
              <span className="text-sm text-ink/70">
                {STATE_LABEL[s.state]}
                {s.at && ` · ${indiaTime(s.at)}`}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** /requests/[id]: one of the customer's own mechanic requests with its status and status changes (India time). */
export function RequestDetailView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const req = useLoad(`request:${id}`, (signal) => accountApi.request(id, signal));
  const status = req.state.status;
  const unauthorised = status === "error" && req.state.message === "Please log in to see this.";
  useEffect(() => {
    if (unauthorised) router.replace(`/login?next=/requests/${id}`);
  }, [unauthorised, router, id]);

  if (status === "loading" || unauthorised) return <Skeleton className="h-96 rounded-3xl" />;
  if (req.state.status === "error") return <ErrorMessage message={req.state.message} onRetry={req.retry} />;
  return <RequestDetail r={req.state.data} />;
}

function RequestDetail({ r }: { r: RequestDetailType }) {
  const photos = usePhotos(r.session_id);
  return (
    <article aria-labelledby="req-h" className="flex flex-col gap-5 rounded-3xl border border-border bg-white p-5 sm:p-7">
      <div>
        <p className="text-sm font-bold tracking-wide text-orange-text uppercase">Mechanic request</p>
        <h1 id="req-h" className="text-3xl leading-tight font-black tracking-tight text-ink tabular-nums">
          {r.reference}
        </h1>
        <p className="mt-1 text-ink/80">
          {r.vehicle} · sent {shortDate(r.created_at.slice(0, 10))}
          {r.urgent && " · urgent"}
        </p>
      </div>
      <SafetyBanner alerts={photoAlerts(photos)} />
      <section aria-labelledby="status-h">
        <h2 id="status-h" className="mb-3 text-xl font-black text-ink">
          Status: {r.status_label}
        </h2>
        {r.mechanic_first_name && (
          <p className="mb-3 text-ink" data-testid="mechanic">
            Your mechanic: <strong>{r.mechanic_first_name}</strong>
          </p>
        )}
        <Timeline steps={r.timeline} />
      </section>
      {r.updates && r.updates.length > 1 && (
        <section aria-labelledby="updates-h">
          <h2 id="updates-h" className="mb-2 text-lg font-black text-ink">
            Updates
          </h2>
          <ul className="flex flex-col gap-1" data-testid="updates">
            {r.updates.map((u, i) => (
              <li key={`${u.at}-${i}`} className="flex flex-wrap justify-between gap-x-3 text-ink">
                <span>{u.label}</span>
                <time dateTime={u.at} className="text-sm text-ink/70 tabular-nums">
                  {indiaTime(u.at)}
                </time>
              </li>
            ))}
          </ul>
        </section>
      )}
      <dl className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl bg-warm-white p-3">
          <dt className="text-sm font-semibold text-ink/70">Service</dt>
          <dd className="text-ink">{SERVICE[r.service_type]}</dd>
        </div>
        {r.area && (
          <div className="rounded-2xl bg-warm-white p-3">
            <dt className="text-sm font-semibold text-ink/70">Area</dt>
            <dd className="text-ink">{r.area}</dd>
          </div>
        )}
        {r.problem_summary && (
          <div className="rounded-2xl bg-warm-white p-3 sm:col-span-2">
            <dt className="text-sm font-semibold text-ink/70">Problem</dt>
            <dd className="text-ink">{r.problem_summary}</dd>
          </div>
        )}
      </dl>
      <PhotoGallery photos={photos} className="border-0 p-0" />
      <div className="flex flex-wrap gap-x-5">
        {r.session_id && (
          <Link
            href={`/diagnose/${r.session_id}/result`}
            className="inline-flex min-h-11 items-center font-bold text-orange-text underline underline-offset-4"
          >
            See the diagnosis
          </Link>
        )}
        <Link href="/account" className="inline-flex min-h-11 items-center font-bold text-orange-text underline underline-offset-4">
          Back to my account
        </Link>
      </div>
    </article>
  );
}
