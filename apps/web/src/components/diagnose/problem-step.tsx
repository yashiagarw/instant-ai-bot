"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useId, useLayoutEffect, useState } from "react";
import { LoaderCircle, Siren } from "lucide-react";
import { useTranslations } from "next-intl";

import { ErrorMessage } from "@/components/error-message";
import { TopicIcon, useTopicLabel } from "@/components/landing/problem-tiles";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { api, type CarFilter, errorMessage, type Topic } from "@/lib/api";
import { useLocaleHref, useSiteLocale } from "@/i18n/navigation";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";
import { vehicleBody, type VehicleChoice } from "@/lib/vehicle";

const MAX_TEXT = 1000;

export function carFilter(choice: VehicleChoice): CarFilter {
  return choice.kind === "listed"
    ? { variant_id: choice.variant_id }
    : { fuel: choice.unlisted.fuel, transmission: choice.unlisted.transmission };
}

function BetaBadge() {
  const t = useTranslations("diagnose");
  return (
    <span className="rounded-full border border-ink/25 bg-white px-2 py-0.5 text-xs font-bold tracking-wide text-ink/75 uppercase">
      {t("beta")}
      <span className="sr-only">{t("betaSr")}</span>
    </span>
  );
}

/** Step 2: pick a problem tile, an emergency topic or describe the problem. Starts the diagnosis session. */
export function ProblemStep({ vehicle, preselected }: { vehicle: VehicleChoice; preselected?: string | null }) {
  const t = useTranslations("diagnose");
  const tc = useTranslations("common");
  const href = useLocaleHref();
  const locale = useSiteLocale();
  const label = useTopicLabel();
  const router = useRouter();
  const textId = useId();
  const car = carFilter(vehicle);
  const topics = useLoad(`topics:${JSON.stringify(car)}`, (signal) => api.categories(signal, car));
  const [text, setText] = useState("");
  const [starting, setStarting] = useState<string | null>(null); // topic code, or "text"
  const [error, setError] = useState<string | null>(null);
  const [textError, setTextError] = useState<string | null>(null);
  // Next.js keeps this page mounted but hidden after navigating to the questions (React Activity). Reset the
  // "starting" state when it is hidden, so Back in the browser shows usable tiles again.
  useLayoutEffect(() => () => setStarting(null), []);

  async function start(topic: Topic | null) {
    if (starting) return;
    setStarting(topic?.code ?? "text");
    setError(null);
    try {
      const s = await api.createSession({ vehicle: vehicleBody(vehicle), topic_id: topic?.code ?? null, text: text.trim() });
      router.push(href(`/diagnose/${s.session_id}`));
    } catch (e) {
      setError(errorMessage(e));
      setStarting(null);
    }
  }

  function submitText(e: FormEvent) {
    e.preventDefault();
    if (text.trim().length < 3) {
      setTextError(t("describeError"));
      return;
    }
    setTextError(null);
    void start(null);
  }

  const ready = topics.state.status === "ready" ? topics.state.data.topics : [];
  const tiles = ready.filter((t) => t.type === "tile");
  const emergency = ready.filter((t) => t.type === "emergency");
  const inspection = ready.find((t) => t.type === "inspection");
  const picked = preselected ? ready.find((t) => t.code === preselected) : undefined;

  const busy = (code: string) =>
    starting === code ? <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" /> : null;

  return (
    <div className="flex flex-col gap-8" aria-busy={starting !== null}>
      {error && <ErrorMessage message={error} />}
      {starting && (
        <p role="status" className="sr-only">
          {t("starting")}
        </p>
      )}

      {picked && (
        <Button type="button" size="cta" className="self-stretch sm:self-start" disabled={!!starting} onClick={() => start(picked)}>
          {busy(picked.code)}
          {t("continueWith", { topic: label(picked) })}
        </Button>
      )}

      <section aria-labelledby="emergency-heading" className="rounded-3xl border-2 border-danger/30 bg-white p-4 sm:p-5">
        <h2 id="emergency-heading" className="flex items-center gap-2 text-xl font-black text-ink">
          <Siren aria-hidden="true" className="size-6 text-danger" />
          {t("emergency")}
        </h2>
        <p className="mt-1 text-ink/75">{t("emergencyText")}</p>
        {topics.state.status === "loading" && (
          <div className="mt-3 flex flex-wrap gap-2" aria-hidden="true">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-12 w-36 rounded-full" />
            ))}
          </div>
        )}
        {topics.state.status === "ready" && (
          <ul className="mt-3 flex flex-wrap gap-2">
            {emergency.map((topic) => (
              <li key={topic.code}>
                <button
                  type="button"
                  disabled={!!starting}
                  onClick={() => start(topic)}
                  className="flex min-h-12 items-center gap-2 rounded-full border-2 border-ink/15 bg-white px-4 py-2 font-semibold text-ink outline-none hover:border-danger focus-visible:ring-3 focus-visible:ring-ring disabled:opacity-60"
                >
                  {busy(topic.code) ?? <TopicIcon code={topic.code} className="size-5 text-orange-text" />}
                  <span>{label(topic)}</span>
                  {topic.beta && <BetaBadge />}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="tiles-heading">
        <h2 id="tiles-heading" className="text-2xl font-black tracking-tight text-ink">
          {t("pickClosest")}
        </h2>
        <div className="mt-4">
          {topics.state.status === "loading" && (
            <div aria-busy="true">
              <span role="status" className="sr-only">
                {t("loadingProblems")}
              </span>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {Array.from({ length: 9 }, (_, i) => (
                  <Skeleton key={i} className="h-28 rounded-3xl" />
                ))}
              </div>
            </div>
          )}
          {topics.state.status === "error" && <ErrorMessage message={topics.state.message} onRetry={topics.retry} />}
          {topics.state.status === "ready" && (
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {tiles.map((topic) => (
                <li key={topic.code}>
                  <button
                    type="button"
                    disabled={!!starting}
                    onClick={() => start(topic)}
                    className={cn(
                      "flex h-full min-h-28 w-full flex-col items-start justify-between gap-2 rounded-3xl border-2 border-ink/10 bg-white p-4 text-left outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring disabled:opacity-60",
                      starting === topic.code && "border-cta",
                    )}
                  >
                    <span className="flex w-full items-start justify-between gap-2">
                      {busy(topic.code) ?? <TopicIcon code={topic.code} className="size-7 text-orange-text" />}
                      {topic.beta && <BetaBadge />}
                    </span>
                    {/* Both languages on every tile: the page's language first. */}
                    <span>
                      <span lang={locale} className="block font-bold text-ink">
                        {label(topic)}
                      </span>
                      <span lang={locale === "hi" ? "en" : "hi"} className="block text-sm text-ink/70">
                        {locale === "hi" ? topic.label : topic.label_hi}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <form onSubmit={submitText} noValidate className="flex flex-col gap-3">
        <label htmlFor={textId} className="text-2xl font-black tracking-tight text-ink">
          {t("describe")}
        </label>
        <p id={`${textId}-hint`} className="text-ink/75">
          {t("describeHint")}
        </p>
        <textarea
          id={textId}
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={MAX_TEXT}
          rows={3}
          aria-describedby={`${textId}-hint${textError ? ` ${textId}-error` : ""}`}
          aria-invalid={textError ? true : undefined}
          className="rounded-3xl border-2 border-ink/15 bg-white p-4 text-lg text-ink outline-none focus-visible:border-cta focus-visible:ring-3 focus-visible:ring-ring/40 aria-invalid:border-orange-text"
        />
        {textError && (
          <p id={`${textId}-error`} role="alert" className="text-sm font-semibold text-orange-text">
            {textError}
          </p>
        )}
        <Button type="submit" size="cta" variant="outline" className="self-stretch border-2 border-ink/15 bg-white text-ink sm:self-start" disabled={!!starting}>
          {busy("text")}
          {tc("continue")}
        </Button>
      </form>

      {inspection && (
        <p className="text-ink/80">
          {t("checkUp")}{" "}
          <button
            type="button"
            disabled={!!starting}
            onClick={() => start(inspection)}
            className="inline-flex min-h-11 items-center rounded-full font-bold text-orange-text underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
          >
            {label(inspection)}
          </button>
        </p>
      )}
    </div>
  );
}
