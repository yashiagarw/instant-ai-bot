"use client";

import { useEffect, useState } from "react";
import { CircleMinus, CircleCheck } from "lucide-react";
import { useTranslations } from "next-intl";

import { Skeleton } from "@/components/skeleton";
import { type Confidence, type Explanation, type RankedFault, streamExplanations } from "@/lib/api";
import { cn } from "@/lib/utils";

const STEPS: Record<Confidence, number> = { high: 3, medium: 2, low: 1 };

/** Confidence as a word with a 3-step meter and the reason for it. The meter is a real meter for screen readers
 * (role="meter", 1 to 3, with the word as its value text); the word itself is shown too. */
export function ConfidenceMeter({ level, reason }: { level: Confidence; reason: string }) {
  const t = useTranslations("result.confidence");
  const word = t(level);
  return (
    <div data-testid="confidence" className="flex flex-col gap-1.5">
      <div className="flex items-center gap-3">
        <span
          role="meter"
          aria-label={t("label")}
          aria-valuemin={1}
          aria-valuemax={3}
          aria-valuenow={STEPS[level]}
          aria-valuetext={t("steps", { level: word, n: STEPS[level] })}
          className="flex gap-1"
        >
          {[1, 2, 3].map((step) => (
            <span
              key={step}
              data-filled={step <= STEPS[level] || undefined}
              className={cn("h-2.5 w-7 rounded-full", step <= STEPS[level] ? "bg-cta" : "bg-ink/15")}
            />
          ))}
        </span>
        <p className="font-bold text-ink" aria-hidden="true">
          {word}
          <span className="sr-only"> {t("outOf", { n: STEPS[level] })}</span>
        </p>
      </div>
      {/* The reason comes from the engine in English. */}
      {reason && (
        <p className="text-ink/80" lang="en">
          {reason}
        </p>
      )}
    </div>
  );
}

/** The explanations stream for a session: cause key -> explanation (an LLM one replaces its template). */
export function useExplanations(sessionId: string) {
  const [items, setItems] = useState<Record<string, Explanation>>({});
  const [status, setStatus] = useState<"loading" | "done" | "error">("loading");
  useEffect(() => {
    const ctrl = new AbortController();
    streamExplanations(sessionId, (e) => setItems((prev) => ({ ...prev, [e.fault_key]: e })), ctrl.signal)
      .then(() => setStatus("done"))
      .catch(() => {
        if (!ctrl.signal.aborted) setStatus("error");
      });
    return () => ctrl.abort();
  }, [sessionId]);
  return { items, status };
}

/** A cause's explanation, or a placeholder while it streams. Nothing when it could not be loaded (the evidence
 * list below still says why). */
export function CauseExplanation({ explanation, loading }: { explanation?: Explanation; loading: boolean }) {
  if (explanation?.text) {
    return (
      <p data-testid="explanation" data-source={explanation.source} className="text-lg text-ink">
        {explanation.text}
      </p>
    );
  }
  if (!loading) return null;
  return (
    <div aria-hidden="true" className="flex flex-col gap-2">
      <Skeleton className="h-4 w-full rounded-full" />
      <Skeleton className="h-4 w-2/3 rounded-full" />
    </div>
  );
}

/** Reasons for the cause, then what doesn't fit it. */
export function EvidenceList({ fault, headingLevel = 3 }: { fault: RankedFault; headingLevel?: 3 | 4 }) {
  const t = useTranslations("result");
  const H = headingLevel === 3 ? "h3" : "h4";
  const items = fault.evidence_items ?? [];
  const forIt = items.filter((e) => e.supports);
  const against = items.filter((e) => !e.supports);
  if (!items.length) return null;
  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-warm-white p-4">
      {forIt.length > 0 && (
        <section>
          <H className="font-bold text-ink">{t("whyWeThink")}</H>
          <ul className="mt-2 flex flex-col gap-1.5">
            {forIt.map((e, i) => (
              <li key={i} className="flex gap-2 text-ink/90">
                <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-success" />
                <span>{e.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {against.length > 0 && (
        <section>
          <H className="font-bold text-ink">{t("whatDoesntFit")}</H>
          <ul className="mt-2 flex flex-col gap-1.5">
            {against.map((e, i) => (
              <li key={i} className="flex gap-2 text-ink/90">
                <CircleMinus aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-ink/60" />
                <span>{e.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
