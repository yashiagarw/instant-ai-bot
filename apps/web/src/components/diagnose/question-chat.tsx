"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChevronLeft, LoaderCircle } from "lucide-react";

import { CarSummary } from "@/components/diagnose/car-summary";
import { ErrorMessage } from "@/components/error-message";
import { SafetyBanner } from "@/components/safety-banner";
import { Skeleton } from "@/components/skeleton";
import { Stepper } from "@/components/stepper";
import { Button } from "@/components/ui/button";
import { type AnswerOut, api, errorMessage, type Option } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

const NOT_SURE = "not_sure";

function ChatSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true">
      <span role="status" className="sr-only">
        Loading your questions…
      </span>
      <Skeleton className="h-14 rounded-2xl" />
      <Skeleton className="h-64 rounded-3xl" />
    </div>
  );
}

/** One question at a time. Answers go to the API; the next question, new safety alerts or the result come back. */
export function QuestionChat() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const router = useRouter();
  const initial = useLoad(`session:${sessionId}`, (signal) => api.session(sessionId, signal));
  const [latest, setLatest] = useState<AnswerOut | null>(null);
  const [sending, setSending] = useState<string | null>(null); // option id being sent, or "back"
  const [error, setError] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const start = initial.state.status === "ready" ? initial.state.data : null;
  const turn: AnswerOut | null = latest ?? start;
  const resultUrl = `/diagnose/${sessionId}/result`;

  // Finished (answers done, or a safety stop): the result page shows the safety banner first.
  useEffect(() => {
    if (turn?.done) router.replace(resultUrl);
  }, [turn?.done, router, resultUrl]);

  // Each new question gets focus, so keyboard and screen reader users start reading it.
  const questionKey = turn?.question ? `${turn.question.id}:${turn.progress.question_number}` : null;
  useEffect(() => {
    if (questionKey && latest) headingRef.current?.focus();
  }, [questionKey, latest]);

  async function send(action: () => Promise<AnswerOut>, key: string) {
    if (sending) return;
    setSending(key);
    setError(null);
    try {
      setLatest(await action());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSending(null);
    }
  }

  if (initial.state.status === "loading") return <ChatSkeleton />;
  if (initial.state.status === "error") return <ErrorMessage message={initial.state.message} onRetry={initial.retry} />;
  if (!start || !turn) return null;

  const q = turn.question;
  const options = q?.options.filter((o) => !o.not_sure) ?? [];
  const notSure = q?.options.find((o) => o.not_sure);
  const { question_number: number, questions_about: about } = turn.progress;
  const answer = (o: Option) =>
    send(() => api.answer(sessionId, q!.id, o.not_sure ? NOT_SURE : o.id), String(o.id));

  return (
    <div className="flex flex-col gap-6">
      <div className="sticky top-16 z-10 -mx-4 border-b border-border bg-warm-white/95 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
        <CarSummary vehicle={start.vehicle} topic={start.topic} />
      </div>
      <Stepper current="Questions" />

      <SafetyBanner alerts={turn.safety_alerts} id="chat-safety" />
      {error && <ErrorMessage message={error} />}

      {!q && (
        <div className="flex flex-col items-start gap-3">
          <p role="status" className="text-lg text-ink">
            Getting your result…
          </p>
          <Button asChild size="cta">
            <Link href={resultUrl}>See your result</Link>
          </Button>
        </div>
      )}

      {q && (
        <section
          key={questionKey}
          aria-labelledby="question-heading"
          className="rounded-3xl border border-border bg-white p-5 shadow-sm duration-200 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 sm:p-7"
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-ink/70" aria-live="polite">
              Question {number} of about {about}
            </p>
            {number > 1 ? (
              <Button
                type="button"
                variant="ghost"
                className="h-11 px-3 text-base font-semibold text-orange-text"
                disabled={!!sending}
                onClick={() => send(() => api.undo(sessionId), "back")}
              >
                {sending === "back" ? (
                  <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
                ) : (
                  <ChevronLeft aria-hidden="true" className="size-5" />
                )}
                Back
              </Button>
            ) : (
              <Button asChild variant="ghost" className="h-11 px-3 text-base font-semibold text-orange-text">
                <Link href="/diagnose?step=problem">
                  <ChevronLeft aria-hidden="true" className="size-5" />
                  Change problem
                </Link>
              </Button>
            )}
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-ink/10" aria-hidden="true">
            <div
              className="h-full rounded-full bg-cta transition-[width] duration-300 motion-reduce:transition-none"
              style={{ width: `${Math.min(100, Math.round(((number - 1) / about) * 100))}%` }}
            />
          </div>

          <h1
            id="question-heading"
            ref={headingRef}
            tabIndex={-1}
            className="mt-5 text-2xl leading-snug font-black tracking-tight text-ink outline-none sm:text-3xl"
          >
            {q.text}
          </h1>

          <ul className="mt-5 flex flex-col gap-2.5">
            {options.map((o) => {
              const before = turn.previous_option_id !== undefined && String(turn.previous_option_id) === String(o.id);
              return (
                <li key={o.id}>
                  <button
                    type="button"
                    disabled={!!sending}
                    aria-describedby={before ? "previous-answer" : undefined}
                    onClick={() => answer(o)}
                    className={cn(
                      "flex min-h-14 w-full items-center gap-3 rounded-2xl border-2 border-ink/15 bg-white px-4 py-3 text-left text-lg font-semibold text-ink outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring disabled:opacity-60",
                      before && "border-orange-text bg-[#ffe6d3]",
                    )}
                  >
                    <span className="flex-1">{o.label}</span>
                    {sending === String(o.id) && (
                      <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
          {turn.previous_option_id !== undefined && turn.previous_option_id !== null && (
            <p id="previous-answer" className="mt-2 text-sm text-ink/70">
              Your earlier answer is highlighted. Pick it again or choose another.
            </p>
          )}
          {notSure && (
            <Button
              type="button"
              variant="outline"
              className="mt-4 h-12 w-full border-2 border-ink/15 bg-white text-base font-semibold text-ink sm:w-auto sm:px-6"
              disabled={!!sending}
              onClick={() => answer(notSure)}
            >
              {sending === String(notSure.id) && (
                <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
              )}
              Not sure
            </Button>
          )}
        </section>
      )}
    </div>
  );
}
