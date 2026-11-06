"use client";

import { useId, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

/** "Was this helpful?" Yes / No with an optional comment, sent once. */
export function FeedbackForm({ sessionId }: { sessionId: string }) {
  const t = useTranslations("result.feedback");
  const id = useId();
  const [helpful, setHelpful] = useState<boolean | null>(null);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (helpful === null) return;
    setState("sending");
    setError(null);
    try {
      await api.feedback(sessionId, helpful, comment.trim());
      setState("sent");
    } catch (e) {
      setError(errorMessage(e));
      setState("idle");
    }
  }

  if (state === "sent") {
    return (
      <p role="status" className="rounded-3xl border border-border bg-white p-5 font-semibold text-ink">
        {t("thanks")}
      </p>
    );
  }

  const choice = (value: boolean, label: string, Icon: typeof ThumbsUp) => (
    <button
      type="button"
      aria-pressed={helpful === value}
      onClick={() => setHelpful(value)}
      className={cn(
        "flex min-h-12 items-center gap-2 rounded-full border-2 border-ink/15 bg-white px-5 font-semibold text-ink outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring",
        helpful === value && "border-orange-text bg-[#ffe6d3]",
      )}
    >
      <Icon aria-hidden="true" className="size-5" />
      {label}
    </button>
  );

  return (
    <section aria-labelledby={`${id}-heading`} className="rounded-3xl border border-border bg-white p-5">
      <h2 id={`${id}-heading`} className="text-xl font-black text-ink">
        {t("title")}
      </h2>
      <div className="mt-3 flex gap-2">
        {choice(true, t("yes"), ThumbsUp)}
        {choice(false, t("no"), ThumbsDown)}
      </div>
      {helpful !== null && (
        <div className="mt-4 flex flex-col gap-2">
          <label htmlFor={`${id}-comment`} className="font-semibold text-ink">
            {t("comment")}
          </label>
          <textarea
            id={`${id}-comment`}
            value={comment}
            maxLength={1000}
            rows={3}
            onChange={(e) => setComment(e.target.value)}
            className="rounded-2xl border-2 border-ink/15 bg-white p-3 text-ink outline-none focus-visible:border-cta focus-visible:ring-3 focus-visible:ring-ring/40"
          />
          {error && (
            <p role="alert" className="text-sm font-semibold text-orange-text">
              {error}
            </p>
          )}
          <Button
            type="button"
            variant="outline"
            className="h-12 self-start border-2 border-ink/15 bg-white px-6 text-base font-semibold text-ink"
            disabled={state === "sending"}
            onClick={send}
          >
            {t("send")}
          </Button>
        </div>
      )}
    </section>
  );
}
