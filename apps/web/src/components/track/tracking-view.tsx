"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { LoaderCircle, Phone } from "lucide-react";

import { Timeline } from "@/components/account/request-detail-view";
import { ErrorMessage } from "@/components/error-message";
import { AlertsButton } from "@/components/notify/alerts-button";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { errorMessage, trackingApi, type Tracking } from "@/lib/api";

const CLOSED = new Set(["completed", "cancelled"]);

/**
 * /track/[id]: live status of a request for the person who made it (their account, or this browser). Polls every
 * few seconds while the page is visible (plain requests: they work through the proxy and on patchy mobile data).
 * Shows the mechanic's first name and photo, their own arrival estimate, and a masked call button. Never a distance:
 * locations are only rough pincode centres.
 */
export function TrackingView() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Tracking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [calling, setCalling] = useState(false);
  const [callNote, setCallNote] = useState<string | null>(null);

  const load = useCallback(
    (signal?: AbortSignal) =>
      trackingApi
        .get(id, signal)
        .then((t) => {
          setData(t);
          setError(null);
        })
        .catch((e) => {
          if (!signal?.aborted) setError(errorMessage(e));
        }),
    [id],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    void load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  const closed = data ? CLOSED.has(data.status) : false;
  const every = (data?.poll_seconds ?? 10) * 1000;
  useEffect(() => {
    if (closed) return;
    const timer = setInterval(() => document.visibilityState === "visible" && void load(), every);
    const back = () => document.visibilityState === "visible" && void load();
    document.addEventListener("visibilitychange", back);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", back);
    };
  }, [load, every, closed]);

  async function call() {
    setCalling(true);
    setCallNote(null);
    try {
      setCallNote((await trackingApi.call(id)).message);
    } catch (e) {
      setCallNote(errorMessage(e));
    } finally {
      setCalling(false);
    }
  }

  if (!data) {
    return error ? <ErrorMessage message={error} onRetry={() => void load()} /> : <Skeleton className="h-96 rounded-3xl" />;
  }
  return (
    <article aria-labelledby="track-h" className="flex flex-col gap-5 rounded-3xl border border-border bg-white p-5 sm:p-7">
      <div>
        <p className="text-sm font-bold tracking-wide text-orange-text uppercase">Live status · {data.reference}</p>
        <h1 id="track-h" className="text-3xl leading-tight font-black tracking-tight text-ink" aria-live="polite" data-testid="track-status">
          {data.status_label}
        </h1>
        {!closed && <p className="mt-1 text-sm text-ink/70">This page updates by itself.</p>}
      </div>

      {data.mechanic && (
        <section aria-label="Your mechanic" className="flex items-center gap-4 rounded-2xl bg-warm-white p-4" data-testid="track-mechanic">
          {data.mechanic.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link from the private bucket
            <img src={data.mechanic.photo_url} alt={`Photo of ${data.mechanic.first_name}`} className="size-16 rounded-full object-cover" />
          ) : (
            <span aria-hidden="true" className="flex size-16 items-center justify-center rounded-full bg-ink text-2xl font-black text-white">
              {data.mechanic.first_name.slice(0, 1)}
            </span>
          )}
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-ink/70">Your mechanic</span>
            <span className="text-2xl font-black text-ink">{data.mechanic.first_name}</span>
            {data.eta_minutes !== null && (
              <span className="text-lg font-bold text-orange-text" data-testid="track-eta">
                {data.eta_minutes <= 1 ? "Arriving any minute" : `Arriving in about ${data.eta_minutes} minutes`}
              </span>
            )}
          </div>
        </section>
      )}

      {data.can_call && (
        <div className="flex flex-col gap-2">
          <Button type="button" size="cta" onClick={call} disabled={calling} className="self-stretch sm:self-start">
            {calling ? <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" /> : <Phone aria-hidden="true" className="size-5" />}
            Call {data.mechanic?.first_name ?? "your mechanic"}
          </Button>
          <p className="text-sm text-ink/70">
            We ring your phone first, then connect you. Neither of you sees the other&apos;s number.
          </p>
          {callNote && (
            <p role="status" className="font-semibold text-ink">
              {callNote}
            </p>
          )}
        </div>
      )}

      <section aria-labelledby="track-steps">
        <h2 id="track-steps" className="mb-3 text-xl font-black text-ink">
          Progress
        </h2>
        <Timeline steps={data.timeline} />
      </section>
      {!closed && <AlertsButton />}
      {error && <p className="text-sm text-ink/70">Couldn&apos;t refresh just now: {error}</p>}
      <Link href="/" className="inline-flex min-h-11 items-center font-bold text-orange-text underline underline-offset-4">
        Home
      </Link>
    </article>
  );
}
