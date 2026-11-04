"use client";

import { useId, useState } from "react";
import { Bell } from "lucide-react";

import { ErrorMessage } from "@/components/error-message";
import { AlertsButton } from "@/components/notify/alerts-button";
import { Skeleton } from "@/components/skeleton";
import { errorMessage, notifyApi, type NotificationChoices as Choices } from "@/lib/api";
import { useLoad } from "@/lib/use-load";

/** "Updates about my requests": SMS on / off, alerts in this browser, and the WhatsApp opt-in with its wording. */
export function NotificationChoices() {
  const id = useId();
  const load = useLoad("me:notifications", (signal) => notifyApi.choices(signal));
  const [saved, setSaved] = useState<Choices | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(change: () => Promise<Choices>) {
    setBusy(true);
    setError(null);
    try {
      setSaved(await change());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const state = load.state;
  const c = saved ?? (state.status === "ready" ? state.data : null);
  return (
    <section aria-labelledby={`${id}-h`} className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-5" data-testid="notification-choices">
      <h2 id={`${id}-h`} className="flex items-center gap-2 text-xl font-black text-ink">
        <Bell aria-hidden="true" className="size-6 text-orange-text" />
        Updates about my requests
      </h2>
      {state.status === "loading" && <Skeleton className="h-24 rounded-2xl" />}
      {state.status === "error" && <ErrorMessage message={state.message} onRetry={load.retry} />}
      {c && (
        <>
          <Toggle
            id={`${id}-sms`}
            label="SMS updates"
            hint="Mechanic assigned, on the way, arrived and job done."
            checked={c.sms}
            disabled={busy}
            onChange={(on) => save(() => notifyApi.setChoices({ sms: on }))}
          />
          <Toggle
            id={`${id}-whatsapp`}
            label="WhatsApp updates"
            hint={c.whatsapp.consent_text}
            checked={c.whatsapp.opted_in}
            disabled={busy}
            onChange={(on) => save(() => notifyApi.setWhatsapp(on, on ? c.whatsapp.consent_text_version : undefined))}
          />
          <AlertsButton onChange={(on) => save(() => notifyApi.setChoices({ push: on }))} />
        </>
      )}
      {error && <ErrorMessage message={error} />}
    </section>
  );
}

function Toggle({
  id,
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  disabled: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <label
      htmlFor={id}
      className="flex min-h-14 cursor-pointer items-start gap-3 rounded-2xl bg-warm-white p-4 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring"
    >
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-6 shrink-0 accent-cta outline-none"
      />
      <span className="flex flex-col">
        <span className="font-bold text-ink">{label}</span>
        <span className="text-sm text-ink/80">{hint}</span>
      </span>
    </label>
  );
}
