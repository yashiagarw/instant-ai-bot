"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useId, useState } from "react";
import { ChevronDown, CircleHelp, RotateCcw, ShieldAlert, Truck, Wrench } from "lucide-react";
import { useTranslations } from "next-intl";

import { ResultCar } from "@/components/car3d/result-car";
import { CarSummary } from "@/components/diagnose/car-summary";
import { MotionCta } from "@/components/motion/motion-cta";
import { ErrorMessage } from "@/components/error-message";
import { PhotoGallery, photoAlerts, usePhotos } from "@/components/diagnose/photo-findings";
import { PartsSection } from "@/components/parts/parts-section";
import { AreaPicker } from "@/components/result/area-picker";
import { EstimateCard, type EstimateState } from "@/components/result/estimate-card";
import { CoverageBadge } from "@/components/result/coverage-badge";
import { CauseExplanation, ConfidenceMeter, EvidenceList, useExplanations } from "@/components/result/explanations";
import { FeedbackForm } from "@/components/result/feedback-form";
import { SafetyBanner } from "@/components/safety-banner";
import { DISCLAIMER } from "@/components/site-footer";
import { Skeleton } from "@/components/skeleton";
import { Stepper } from "@/components/stepper";
import { Button } from "@/components/ui/button";
import {
  api,
  mediaUrl,
  partsApi,
  type Area,
  type Estimates,
  type RankedFault,
  type ResultOut,
  type RoadsideVerdict,
} from "@/lib/api";
import { repeats, roadsideText, towingText } from "@/lib/format";
import en from "@/i18n/messages/site.en.json";
import { useLocaleHref, useSiteLocale } from "@/i18n/navigation";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

// Roadside verdicts are safety and towing advice: English (lang="en") on the Hindi pages too, until reviewed Hindi
// exists (Phase 5.5).
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

/** Text from the dataset or the engine is English: marked so on the Hindi pages (screen readers, fonts). */
function useEnglishContent(): "en" | undefined {
  return useSiteLocale() === "hi" ? "en" : undefined;
}

/** A fault's name: the reviewed Hindi one on Hindi pages when it exists, else English. Never machine-translated. */
function useFaultName() {
  const locale = useSiteLocale();
  return (f: RankedFault): { text: string; lang?: "en" | "hi" } =>
    locale === "hi" && f.name_hi ? { text: f.name_hi, lang: "hi" } : { text: f.name, lang: locale === "hi" ? "en" : undefined };
}

function List({ items, ordered = false, lang }: { items: string[]; ordered?: boolean; lang?: string }) {
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag lang={lang} className={cn("mt-2 flex flex-col gap-1.5 pl-5 text-ink/90", ordered ? "list-decimal" : "list-disc")}>
      {items.map((t, i) => (
        <li key={i}>{t}</li>
      ))}
    </Tag>
  );
}

const SHOWN_STEPS = 5;

/** The mechanic's steps: the first few, the rest behind "Show all". */
function Steps({ items }: { items: string[] }) {
  const t = useTranslations("result");
  const lang = useEnglishContent();
  const id = useId();
  const [all, setAll] = useState(false);
  const hidden = items.length - SHOWN_STEPS;
  return (
    <>
      <ol id={id} lang={lang} className="mt-2 flex list-decimal flex-col gap-1.5 pl-5 text-ink/90">
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
          {all ? t("showFewerSteps") : t("showAllSteps", { count: items.length })}
        </button>
      )}
    </>
  );
}

/** Steps, what you can do, what the mechanic will do and pictures; sections with no content are left out. */
function FaultDetails({ fault, verdict, headingLevel = 2 }: { fault: RankedFault; verdict: RoadsideVerdict; headingLevel?: 2 | 3 }) {
  const t = useTranslations("result");
  const lang = useEnglishContent();
  const name = useFaultName()(fault).text;
  const H = headingLevel === 2 ? "h2" : "h3";
  const advice = verdict !== "unknown" ? VERDICT[verdict].advice : null;
  return (
    <div className="flex flex-col gap-5">
      {fault.media.length > 0 && (
        <section aria-label={t("illustrations", { name })}>
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
                        alt={m.caption ? t("illustrationAlt", { caption: m.caption }) : t("illustrationFor", { name })}
                        loading="lazy"
                        className="aspect-[4/3] w-full bg-warm-white object-contain"
                      />
                      <span className="absolute top-2 left-2 rounded-full bg-ink/80 px-2 py-0.5 text-xs font-bold text-white">
                        {t("illustration")}
                      </span>
                    </div>
                    {m.caption && (
                      <figcaption lang={lang} className="p-3 text-sm text-ink/80">
                        {m.caption}
                      </figcaption>
                    )}
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
            {t("repairRecommendation")}
          </H>
          {advice && (
            <p lang="en" className="font-semibold text-ink">
              {advice}
            </p>
          )}
          {fault.what_you_can_do.length > 0 && (
            <div>
              <p className="font-bold text-ink">{t("whatYouCanDo")}</p>
              <List items={fault.what_you_can_do} lang={lang} />
            </div>
          )}
          {fault.what_the_mechanic_will_do.length > 0 && (
            <div>
              <p className="font-bold text-ink">{t("whatMechanicWillDo")}</p>
              <Steps items={fault.what_the_mechanic_will_do} />
            </div>
          )}
        </section>
      )}
      {fault.diagnostic_steps.length > 0 && (
        <section>
          <H className="text-lg font-black text-ink">{t("howChecked")}</H>
          <List items={fault.diagnostic_steps} ordered lang={lang} />
        </section>
      )}
    </div>
  );
}

function RequestButton({ sessionId, sticky = false }: { sessionId: string; sticky?: boolean }) {
  const tc = useTranslations("common");
  const button = (
    <MotionCta className="flex *:flex-1 md:*:flex-none">
      <Button asChild size="cta" className="w-full md:w-auto">
        <Link href={`/request?session=${sessionId}`}>{tc("requestMechanic")}</Link>
      </Button>
    </MotionCta>
  );
  if (!sticky) return button;
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-white/95 p-3 backdrop-blur md:hidden">
      {button}
    </div>
  );
}

/** Estimates for the result's causes in the chosen area (GET /api/estimates); re-fetched when the area changes. */
function useEstimates(sessionId: string, area: Area) {
  const loaded = useLoad(`estimates:${sessionId}:${JSON.stringify(area)}`, (signal) =>
    partsApi.estimates(sessionId, area, signal),
  );
  const data: Estimates | null = loaded.state.status === "ready" ? loaded.state.data : null;
  const stateFor = (faultKey: string): EstimateState =>
    loaded.state.status === "ready"
      ? { status: "ready", estimate: loaded.state.data.estimates.find((e) => e.fault_key === faultKey) }
      : loaded.state.status === "loading"
        ? { status: "loading" }
        : { status: "error" };
  return { data, stateFor };
}

function useAreaNote() {
  const t = useTranslations("result.area");
  return (data: Estimates | null): string => {
    if (!data) return t("metro");
    if (data.zone.label) return t("labourFor", { zone: data.zone.label });
    return data.zone.source === "pincode" ? data.zone.note : t("metro");
  };
}

function Result({ r }: { r: ResultOut }) {
  const t = useTranslations("result");
  const tc = useTranslations("common");
  const href = useLocaleHref();
  const lang = useEnglishContent();
  const faultName = useFaultName();
  const areaNote = useAreaNote();
  const [top, ...others] = r.ranked;
  const topName = top ? faultName(top) : null;
  const [area, setArea] = useState<Area>(null);
  const estimates = useEstimates(r.session_id, area);
  const zoneLabel = estimates.data?.zone.label ?? null;
  const verifying = estimates.data?.estimates.some((e) => e.flags?.needs_check) ?? false;
  const explanations = useExplanations(r.session_id);
  const photos = usePhotos(r.session_id);
  const streaming = explanations.status === "loading";
  const verdict = r.roadside.verdict;
  const roadText = roadsideText(r.roadside.text);
  const towingRaw = towingText(r.roadside.towing);
  const towing = towingRaw && !repeats(roadText, towingRaw) ? towingRaw : "";
  const fastTrack = r.mode === "fast_track" || r.mode === "inspect";
  return (
    <div className="flex flex-col gap-6 pb-24 md:pb-0">
      <SafetyBanner alerts={[...r.safety_alerts, ...photoAlerts(photos, r.safety_alerts)]} id="result-safety" />
      <Stepper current="Result" />

      {r.status === "in_progress" && (
        <p className="rounded-2xl border border-border bg-white p-4 text-ink">
          {t("notFinished")}{" "}
          <Link href={href(`/diagnose/${r.session_id}`)} className="font-bold text-orange-text underline underline-offset-4">
            {t("continueQuestions")}
          </Link>
        </p>
      )}

      <header className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-5">
        <h1 className="text-3xl leading-tight font-black tracking-tight text-ink sm:text-4xl">{t("title")}</h1>
        <CarSummary vehicle={r.vehicle} topic={r.topic} />
        <CoverageBadge level={r.coverage_level} />
      </header>

      <div lang={lang} className="contents">
        <PhotoGallery photos={photos} />
      </div>

      {fastTrack && (
        <section aria-labelledby="tips-heading" className="flex flex-col gap-4 rounded-3xl border-2 border-cta bg-white p-5">
          <h2 id="tips-heading" className="flex items-center gap-2 text-2xl font-black text-ink">
            <ShieldAlert aria-hidden="true" className="size-6 text-orange-text" />
            {r.mode === "inspect" ? t("inspectionTitle") : <span lang="en">Stay safe while help comes</span>}
          </h2>
          {/* Safety tips: English until reviewed Hindi exists (never machine-translated). */}
          {r.safety_tips.length > 0 && <List items={r.safety_tips} lang="en" />}
          <RequestButton sessionId={r.session_id} />
        </section>
      )}

      {!top && !fastTrack && (
        <p className="rounded-3xl border border-border bg-white p-5 text-ink">
          {t("couldNotNarrow")}
        </p>
      )}

      {top && (
        <article aria-labelledby="top-cause" className="flex flex-col gap-5 rounded-3xl border-2 border-cta bg-white p-5 sm:p-7">
          <div className="flex flex-col gap-3">
            <p className="text-sm font-bold tracking-wide text-orange-text uppercase">{t("mostLikely")}</p>
            <h2 id="top-cause" lang={topName?.lang} className="text-3xl leading-tight font-black tracking-tight text-ink">
              {topName?.text}
            </h2>
            <ConfidenceMeter level={top.confidence} reason={top.confidence_reason} />
          </div>
          <div aria-live="polite" lang={lang}>
            <CauseExplanation explanation={explanations.items[top.fault_key]} loading={streaming} />
          </div>
          <EvidenceList fault={top} />

          {verdict !== "unknown" && (
            <section lang="en" className={cn("rounded-2xl border p-4", VERDICT[verdict].tone)} data-testid="roadside">
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

          {r.vehicle.price_segment && (
            <div className="flex flex-col gap-2">
              <AreaPicker area={area} onChange={setArea} note={areaNote(estimates.data)} />
              {verifying && (
                <p className="px-1 text-sm text-ink/75" data-testid="verifying-note">
                  {t("verifyingPrices")}
                </p>
              )}
            </div>
          )}
          <EstimateCard
            state={estimates.stateFor(top.fault_key)}
            fallback={top.cost}
            repairTime={top.repair_time}
            sessionId={r.session_id}
            zoneLabel={zoneLabel}
            segmentKnown={!!r.vehicle.price_segment}
          />
          <FaultDetails fault={top} verdict={verdict} />
        </article>
      )}

      {/* The diagnosed system on a 3D car (never in the question chat). */}
      {top && <ResultCar category={top.category} />}

      {/* Parts catalogue and photo findings: English only for now (shared with the English /parts and request pages). */}
      {top && !fastTrack && (
        <PartsSection
          lang={lang}
          faultKey={top.fault_key}
          faultName={top.name}
          variantId={r.vehicle.variant_id}
          segment={r.vehicle.price_segment}
        />
      )}

      {r.uncertainty?.length > 0 && (
        <section aria-labelledby="uncertainty-heading" className="flex gap-3 rounded-3xl border border-border bg-white p-5">
          <CircleHelp aria-hidden="true" className="mt-1 size-6 shrink-0 text-orange-text" />
          <div>
            <h2 id="uncertainty-heading" className="text-lg font-black text-ink">
              {t("notCertain")}
            </h2>
            {r.uncertainty.map((u) => (
              <p key={u.code} lang={lang} className="mt-1 text-ink/90">
                {u.message}
              </p>
            ))}
          </div>
        </section>
      )}

      {others.length > 0 && (
        <section aria-labelledby="others-heading" className="flex flex-col gap-3">
          <h2 id="others-heading" className="text-xl font-black text-ink">
            {t("otherCauses")}
          </h2>
          {others.map((f) => (
            <details key={f.fault_key} className="group rounded-3xl border border-border bg-white">
              <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 rounded-3xl p-4 outline-none focus-visible:ring-3 focus-visible:ring-ring">
                <span>
                  <span lang={faultName(f).lang} className="block font-bold text-ink">
                    {faultName(f).text}
                  </span>
                  <span className="text-sm text-ink/70">{t(`confidence.${f.confidence}`)}</span>
                </span>
                <ChevronDown
                  aria-hidden="true"
                  className="size-5 shrink-0 text-ink/60 transition-transform group-open:rotate-180 motion-reduce:transition-none"
                />
              </summary>
              <div className="flex flex-col gap-4 border-t border-border p-4">
                <ConfidenceMeter level={f.confidence} reason={f.confidence_reason} />
                <div aria-live="polite" lang={lang}>
                  <CauseExplanation explanation={explanations.items[f.fault_key]} loading={streaming} />
                </div>
                <EvidenceList fault={f} />
                <EstimateCard
                  state={estimates.stateFor(f.fault_key)}
                  fallback={f.cost}
                  repairTime={f.repair_time}
                  sessionId={r.session_id}
                  zoneLabel={zoneLabel}
                  segmentKnown={!!r.vehicle.price_segment}
                />
                <FaultDetails fault={f} verdict="unknown" headingLevel={3} />
              </div>
            </details>
          ))}
        </section>
      )}

      {!fastTrack && r.if_not_fixed?.length > 0 && (
        <section aria-labelledby="not-fixed" className="rounded-3xl border border-border bg-white p-5">
          <h2 id="not-fixed" className="flex items-center gap-2 text-xl font-black text-ink">
            <RotateCcw aria-hidden="true" className="size-5 text-orange-text" />
            {t("ifNotFixed")}
          </h2>
          <List items={r.if_not_fixed} lang={lang} />
        </section>
      )}

      {!fastTrack && r.safety_tips.length > 0 && (
        <section aria-labelledby="safety-tips" className="rounded-3xl border border-border bg-white p-5">
          <h2 id="safety-tips" lang="en" className="text-xl font-black text-ink">
            Safety tips
          </h2>
          {/* English until reviewed Hindi exists (never machine-translated). */}
          <List items={r.safety_tips} lang="en" />
        </section>
      )}

      {r.answers.length > 0 && (
        <details className="rounded-3xl border border-border bg-white">
          <summary className="flex min-h-14 cursor-pointer items-center rounded-3xl p-4 font-bold text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring">
            {t("yourAnswers", { count: r.answers.length })}
          </summary>
          <dl lang={lang} className="flex flex-col gap-3 border-t border-border p-4">
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
        {/* Every result shows the disclaimer: the standard one in the page's language, any other text as sent. */}
        {!r.disclaimer || r.disclaimer === DISCLAIMER ? (
          tc("disclaimer")
        ) : r.disclaimer === en.result.disclaimer ? (
          t("disclaimer")
        ) : (
          <span lang="en">{r.disclaimer}</span>
        )}
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
  const t = useTranslations("result");
  return (
    <div className="flex flex-col gap-6" aria-busy="true">
      <span role="status" className="sr-only">
        {t("loading")}
      </span>
      <Skeleton className="h-36 rounded-3xl" />
      <Skeleton className="h-80 rounded-3xl" />
      <Skeleton className="h-40 rounded-3xl" />
    </div>
  );
}

// Phase 5.5: the result's text is the page's largest paint, and it comes from the API. Start that request as soon as
// this code arrives in the browser, before React has hydrated the page; ResultView picks the promise up.
let early: { id: string; result: Promise<ResultOut> } | null = null;
if (typeof window !== "undefined") {
  const m = /\/diagnose\/([^/]+)\/result\/?$/.exec(window.location.pathname);
  if (m) {
    const result = api.result(decodeURIComponent(m[1]));
    result.catch(() => undefined); // an error is shown by ResultView (which asks again on Try again)
    early = { id: decodeURIComponent(m[1]), result };
  }
}
function earlyResult(id: string): Promise<ResultOut> | null {
  if (early?.id !== id) return null;
  const { result } = early;
  early = null; // once: Try again and later visits ask the API again
  return result;
}

/** The result page; works on its own from a shared link (everything comes from the session id). */
export function ResultView() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const t = useTranslations("result");
  const href = useLocaleHref();
  const result = useLoad(`result:${sessionId}`, (signal) => earlyResult(sessionId) ?? api.result(sessionId, signal));
  if (result.state.status === "loading") return <ResultSkeleton />;
  if (result.state.status === "error") {
    return (
      <div className="flex flex-col gap-4">
        <ErrorMessage message={result.state.message} onRetry={result.retry} />
        <Link href={href("/diagnose")} className="font-bold text-orange-text underline underline-offset-4">
          {t("startNew")}
        </Link>
      </div>
    );
  }
  return <Result r={result.state.data} />;
}
