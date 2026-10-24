"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useId, useState } from "react";
import { ChevronDown, ShieldAlert, Truck, Wrench } from "lucide-react";

import { CarSummary } from "@/components/diagnose/car-summary";
import { ErrorMessage } from "@/components/error-message";
import { CostCard } from "@/components/result/cost-card";
import { CoverageBadge } from "@/components/result/coverage-badge";
import { FeedbackForm } from "@/components/result/feedback-form";
import { SafetyBanner } from "@/components/safety-banner";
import { DISCLAIMER } from "@/components/site-footer";
import { Skeleton } from "@/components/skeleton";
import { Stepper } from "@/components/stepper";
import { Button } from "@/components/ui/button";
import { api, mediaUrl, type RankedFault, type ResultOut, type RoadsideVerdict } from "@/lib/api";
import { repeats, roadsideText, towingText } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

const VERDICT: Record<Exclude<RoadsideVerdict, "unknown">, { label: string; advice: string; tone: string }> = {
  roadside_fix_possible: {
    label: "Can usually be fixed on the road",
    advice: "You may be able to sort this out yourself or with roadside help.",
    tone: "border-success/30 bg-success-bg text-success",
  },
  roadside_limited: {
    label: "Roadside check, then a garage",
    advice: "A mechanic can check it where the car is, but the repair needs a garage.",
    tone: "border-orange-text/30 bg-warm-white text-orange-text",
  },
  workshop: {
    label: "Needs a garage or a tow",
    advice: "This needs a mechanic at a garage. Don't try to repair it yourself.",
    tone: "border-ink/20 bg-white text-ink",
  },
  do_not_drive: {
    label: "Do not drive: get a tow",
    advice: "Driving could make it worse or be unsafe. Ask for a tow or a mechanic to come to you.",
    tone: "border-danger/40 bg-white text-danger",
  },
};

const CONFIDENCE = { high: "Most likely", medium: "Likely", low: "Possible" } as const;

function List({ items, ordered = false }: { items: string[]; ordered?: boolean }) {
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag className={cn("mt-2 flex flex-col gap-1.5 pl-5 text-ink/90", ordered ? "list-decimal" : "list-disc")}>
      {items.map((t, i) => (
        <li key={i}>{t}</li>
      ))}
    </Tag>
  );
}

const SHOWN_STEPS = 5;

/** The mechanic's steps: the first few, the rest behind "Show all". */
function Steps({ items }: { items: string[] }) {
  const id = useId();
  const [all, setAll] = useState(false);
  const hidden = items.length - SHOWN_STEPS;
  return (
    <>
      <ol id={id} className="mt-2 flex list-decimal flex-col gap-1.5 pl-5 text-ink/90">
        {(all ? items : items.slice(0, SHOWN_STEPS)).map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ol>
      {hidden > 0 && (
        <button
          type="button"
          aria-expanded={all}
          aria-controls={id}
          onClick={() => setAll((v) => !v)}
          className="mt-2 inline-flex min-h-11 items-center rounded-full font-bold text-orange-text underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
        >
          {all ? "Show fewer steps" : `Show all ${items.length} steps`}
        </button>
      )}
    </>
  );
}

/** Steps, what you can do, what the mechanic will do and pictures; sections with no content are left out. */
function FaultDetails({ fault, verdict, headingLevel = 2 }: { fault: RankedFault; verdict: RoadsideVerdict; headingLevel?: 2 | 3 }) {
  const H = headingLevel === 2 ? "h2" : "h3";
  const advice = verdict !== "unknown" ? VERDICT[verdict].advice : null;
  return (
    <div className="flex flex-col gap-5">
      {fault.media.length > 0 && (
        <section aria-label={`Illustrations for ${fault.name}`}>
          <ul className="grid gap-3 sm:grid-cols-2">
            {[...fault.media]
              .sort((a, b) => (a.role === b.role ? 0 : a.role === "main" ? -1 : 1))
              .map((m) => (
                <li key={m.file}>
                  <figure className="overflow-hidden rounded-2xl border border-border bg-white">
                    <div className="relative">
                      {/* eslint-disable-next-line @next/next/no-img-element -- pictures come from the API's /media */}
                      <img
                        src={mediaUrl(m.file)}
                        alt={m.caption ? `Illustration: ${m.caption}` : `Illustration for ${fault.name}`}
                        loading="lazy"
                        className="aspect-[4/3] w-full bg-warm-white object-contain"
                      />
                      <span className="absolute top-2 left-2 rounded-full bg-ink/80 px-2 py-0.5 text-xs font-bold text-white">
                        Illustration
                      </span>
                    </div>
                    {m.caption && <figcaption className="p-3 text-sm text-ink/80">{m.caption}</figcaption>}
                  </figure>
                </li>
              ))}
          </ul>
        </section>
      )}
      {(fault.what_you_can_do.length > 0 || fault.what_the_mechanic_will_do.length > 0) && (
        <section className="flex flex-col gap-4">
          <H className="flex items-center gap-2 text-lg font-black text-ink">
            <Wrench aria-hidden="true" className="size-5 text-orange-text" />
            Repair recommendation
          </H>
          {advice && <p className="font-semibold text-ink">{advice}</p>}
          {fault.what_you_can_do.length > 0 && (
            <div>
              <p className="font-bold text-ink">What you can do</p>
              <List items={fault.what_you_can_do} />
            </div>
          )}
          {fault.what_the_mechanic_will_do.length > 0 && (
            <div>
              <p className="font-bold text-ink">What the mechanic will do</p>
              <Steps items={fault.what_the_mechanic_will_do} />
            </div>
          )}
        </section>
      )}
      {fault.diagnostic_steps.length > 0 && (
        <section>
          <H className="text-lg font-black text-ink">How it&apos;s checked</H>
          <List items={fault.diagnostic_steps} ordered />
        </section>
      )}
    </div>
  );
}

function RequestButton({ sessionId, sticky = false }: { sessionId: string; sticky?: boolean }) {
  const button = (
    <Button asChild size="cta" className="w-full md:w-auto">
      <Link href={`/request?session=${sessionId}`}>Request a Mechanic</Link>
    </Button>
  );
  if (!sticky) return button;
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-white/95 p-3 backdrop-blur md:hidden">
      {button}
    </div>
  );
}

function Result({ r }: { r: ResultOut }) {
  const [top, ...others] = r.ranked;
  const verdict = r.roadside.verdict;
  const roadText = roadsideText(r.roadside.text);
  const towingRaw = towingText(r.roadside.towing);
  const towing = towingRaw && !repeats(roadText, towingRaw) ? towingRaw : "";
  const fastTrack = r.mode === "fast_track" || r.mode === "inspect";
  return (
    <div className="flex flex-col gap-6 pb-24 md:pb-0">
      <SafetyBanner alerts={r.safety_alerts} id="result-safety" />
      <Stepper current="Result" />

      {r.status === "in_progress" && (
        <p className="rounded-2xl border border-border bg-white p-4 text-ink">
          This diagnosis isn&apos;t finished yet, so this is the ranking so far.{" "}
          <Link href={`/diagnose/${r.session_id}`} className="font-bold text-orange-text underline underline-offset-4">
            Continue the questions
          </Link>
        </p>
      )}

      <header className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-5">
        <h1 className="text-3xl leading-tight font-black tracking-tight text-ink sm:text-4xl">Your result</h1>
        <CarSummary vehicle={r.vehicle} topic={r.topic} />
        <CoverageBadge level={r.coverage_level} />
      </header>

      {fastTrack && (
        <section aria-labelledby="tips-heading" className="flex flex-col gap-4 rounded-3xl border-2 border-cta bg-white p-5">
          <h2 id="tips-heading" className="flex items-center gap-2 text-2xl font-black text-ink">
            <ShieldAlert aria-hidden="true" className="size-6 text-orange-text" />
            {r.mode === "inspect" ? "Book an inspection" : "Stay safe while help comes"}
          </h2>
          {r.safety_tips.length > 0 && <List items={r.safety_tips} />}
          <RequestButton sessionId={r.session_id} />
        </section>
      )}

      {!top && !fastTrack && (
        <p className="rounded-3xl border border-border bg-white p-5 text-ink">
          We couldn&apos;t narrow this down from your answers. A mechanic can inspect the car and find the cause.
        </p>
      )}

      {top && (
        <article aria-labelledby="top-cause" className="flex flex-col gap-5 rounded-3xl border-2 border-cta bg-white p-5 sm:p-7">
          <div>
            <p className="text-sm font-bold tracking-wide text-orange-text uppercase">{CONFIDENCE[top.confidence]} cause</p>
            <h2 id="top-cause" className="mt-1 text-3xl leading-tight font-black tracking-tight text-ink">
              {top.name}
            </h2>
          </div>
          {top.evidence.length > 0 && (
            <section className="rounded-2xl bg-warm-white p-4">
              <h3 className="font-bold text-ink">Why we think this</h3>
              <List items={top.evidence} />
            </section>
          )}

          {verdict !== "unknown" && (
            <section className={cn("rounded-2xl border p-4", VERDICT[verdict].tone)} data-testid="roadside">
              <h3 className="flex items-center gap-2 text-lg font-black">
                <Truck aria-hidden="true" className="size-5" />
                {VERDICT[verdict].label}
              </h3>
              {roadText && <p className="mt-1 text-ink/90">{roadText}</p>}
              {towing && (
                <p className="mt-1 text-ink/90">
                  <span className="font-semibold">When to tow:</span> {towing}
                </p>
              )}
            </section>
          )}

          <CostCard cost={top.cost} repairTime={top.repair_time} />
          <FaultDetails fault={top} verdict={verdict} />
        </article>
      )}

      {others.length > 0 && (
        <section aria-labelledby="others-heading" className="flex flex-col gap-3">
          <h2 id="others-heading" className="text-xl font-black text-ink">
            Other possible causes
          </h2>
          {others.map((f) => (
            <details key={f.fault_key} className="group rounded-3xl border border-border bg-white">
              <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 rounded-3xl p-4 outline-none focus-visible:ring-3 focus-visible:ring-ring">
                <span>
                  <span className="block font-bold text-ink">{f.name}</span>
                  <span className="text-sm text-ink/70">{CONFIDENCE[f.confidence]}</span>
                </span>
                <ChevronDown
                  aria-hidden="true"
                  className="size-5 shrink-0 text-ink/60 transition-transform group-open:rotate-180 motion-reduce:transition-none"
                />
              </summary>
              <div className="flex flex-col gap-4 border-t border-border p-4">
                {f.evidence.length > 0 && (
                  <div>
                    <h3 className="font-bold text-ink">Why it could be this</h3>
                    <List items={f.evidence} />
                  </div>
                )}
                <CostCard cost={f.cost} repairTime={f.repair_time} />
                <FaultDetails fault={f} verdict="unknown" headingLevel={3} />
              </div>
            </details>
          ))}
        </section>
      )}

      {!fastTrack && r.safety_tips.length > 0 && (
        <section aria-labelledby="safety-tips" className="rounded-3xl border border-border bg-white p-5">
          <h2 id="safety-tips" className="text-xl font-black text-ink">
            Safety tips
          </h2>
          <List items={r.safety_tips} />
        </section>
      )}

      {r.answers.length > 0 && (
        <details className="rounded-3xl border border-border bg-white">
          <summary className="flex min-h-14 cursor-pointer items-center rounded-3xl p-4 font-bold text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring">
            Your answers ({r.answers.length})
          </summary>
          <dl className="flex flex-col gap-3 border-t border-border p-4">
            {r.answers.map((a, i) => (
              <div key={i}>
                <dt className="text-sm text-ink/70">{a.question}</dt>
                <dd className="font-semibold text-ink">{a.answer}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}

      <p className="rounded-2xl bg-white p-4 text-sm text-ink/80" data-testid="disclaimer">
        {r.disclaimer || DISCLAIMER}
      </p>

      <FeedbackForm sessionId={r.session_id} />

      <div className="hidden md:block">
        <RequestButton sessionId={r.session_id} />
      </div>
      <RequestButton sessionId={r.session_id} sticky />
    </div>
  );
}

function ResultSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true">
      <span role="status" className="sr-only">
        Loading your result…
      </span>
      <Skeleton className="h-36 rounded-3xl" />
      <Skeleton className="h-80 rounded-3xl" />
      <Skeleton className="h-40 rounded-3xl" />
    </div>
  );
}

/** The result page; works on its own from a shared link (everything comes from the session id). */
export function ResultView() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const result = useLoad(`result:${sessionId}`, (signal) => api.result(sessionId, signal));
  if (result.state.status === "loading") return <ResultSkeleton />;
  if (result.state.status === "error") {
    return (
      <div className="flex flex-col gap-4">
        <ErrorMessage message={result.state.message} onRetry={result.retry} />
        <Link href="/diagnose" className="font-bold text-orange-text underline underline-offset-4">
          Start a new diagnosis
        </Link>
      </div>
    );
  }
  return <Result r={result.state.data} />;
}
