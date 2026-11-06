"use client";

import { useId, useState } from "react";
import { Check, LoaderCircle, Pencil } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";

const MAX_TEXT = 1000;

/** One typed message and what we took from it. Only the last one can be corrected, until an option is tapped. */
export interface Note {
  text: string;
  items: string[];
  correctable: boolean;
}

/** "We understood: ..." for one message; tapping it offers to take the message back and edit it. */
function UnderstoodChip({ note, onCorrect, busy }: { note: Note; onCorrect: () => void; busy: boolean }) {
  const t = useTranslations("diagnose");
  const [open, setOpen] = useState(false);
  const panel = useId();
  const understood = note.items.length ? t("understood", { items: note.items.join(" · ") }) : t("addedToDescription");
  const chip =
    "inline-flex min-h-11 max-w-full items-center gap-2 rounded-full border-2 border-orange-text/30 bg-warm-white px-4 py-2 text-left text-base font-semibold text-ink";
  return (
    <li className="flex flex-col items-start gap-2">
      <p className="max-w-full rounded-2xl rounded-br-sm bg-ink/5 px-4 py-2 text-ink">
        <span className="sr-only">{t("youWrote")}</span>
        {note.text}
      </p>
      {note.correctable ? (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panel}
          onClick={() => setOpen((v) => !v)}
          className={`${chip} outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring`}
        >
          <Check aria-hidden="true" className="size-5 shrink-0 text-orange-text" />
          <span className="min-w-0 break-words">{understood}</span>
          <span className="sr-only">{t("tapToCorrect")}</span>
        </button>
      ) : (
        <p className={chip}>
          <Check aria-hidden="true" className="size-5 shrink-0 text-orange-text" />
          <span className="min-w-0 break-words">{understood}</span>
        </p>
      )}
      {note.correctable && open && (
        <div id={panel} className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-white p-3">
          <p className="text-ink">{t("notWhatYouMeant")}</p>
          <Button
            type="button"
            variant="outline"
            className="h-11 border-2 border-ink/15 bg-white px-4 text-base font-semibold text-ink"
            disabled={busy}
            onClick={onCorrect}
          >
            {busy ? (
              <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
            ) : (
              <Pencil aria-hidden="true" className="size-5" />
            )}
            {t("editMessage")}
          </Button>
        </div>
      )}
    </li>
  );
}

/** Type a reply at any time, in English, Hindi or Hinglish. Shows what we understood from each message. */
export function ReplyBox({
  notes,
  draft,
  onDraft,
  onSend,
  onCorrect,
  sending,
  inputRef,
}: {
  notes: Note[];
  draft: string;
  onDraft: (v: string) => void;
  onSend: () => void;
  onCorrect: () => void;
  sending: string | null;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
}) {
  const t = useTranslations("diagnose");
  const id = useId();
  const [error, setError] = useState<string | null>(null);
  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) {
      setError(t("replyError"));
      return;
    }
    setError(null);
    onSend();
  }
  return (
    <section aria-label={t("replyRegion")} className="flex flex-col gap-4">
      {notes.length > 0 && (
        <ul aria-label={t("yourMessages")} aria-live="polite" className="flex flex-col gap-4">
          {notes.map((n, i) => (
            <UnderstoodChip key={i} note={n} onCorrect={onCorrect} busy={sending === "undo-message"} />
          ))}
        </ul>
      )}
      <form onSubmit={submit} noValidate className="flex flex-col gap-3">
        <label htmlFor={id} className="text-lg font-bold text-ink">
          {t("replyLabel")}
        </label>
        <p id={`${id}-hint`} className="text-ink/75">
          {t("replyHint")}
        </p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <textarea
            id={id}
            ref={inputRef}
            value={draft}
            onChange={(e) => onDraft(e.target.value)}
            maxLength={MAX_TEXT}
            rows={2}
            aria-describedby={`${id}-hint${error ? ` ${id}-error` : ""}`}
            aria-invalid={error ? true : undefined}
            className="min-h-14 flex-1 rounded-3xl border-2 border-ink/15 bg-white px-4 py-3 text-lg text-ink outline-none focus-visible:border-cta focus-visible:ring-3 focus-visible:ring-ring/40 aria-invalid:border-orange-text"
          />
          <Button type="submit" size="cta" className="self-stretch text-white sm:self-start" disabled={!!sending}>
            {sending === "message" && (
              <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
            )}
            {t("send")}
          </Button>
        </div>
        {error && (
          <p id={`${id}-error`} role="alert" className="text-sm font-semibold text-orange-text">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
