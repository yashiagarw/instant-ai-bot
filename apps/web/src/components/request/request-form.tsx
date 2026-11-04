"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { CarFront, CircleCheck, LoaderCircle, Phone } from "lucide-react";

import { ChoiceGroup } from "@/components/choice-group";
import { ErrorMessage } from "@/components/error-message";
import { AlertsButton } from "@/components/notify/alerts-button";
import { Skeleton } from "@/components/skeleton";
import { TextField } from "@/components/text-field";
import { Button } from "@/components/ui/button";
import {
  api,
  errorMessage,
  type RequestConfig,
  type ResultOut,
  type ServiceRequestOut,
  type ServiceType,
} from "@/lib/api";
import { useLoad } from "@/lib/use-load";

const SERVICE_TYPES: { value: ServiceType; label: string; hint: string }[] = [
  { value: "at_location", label: "At my location", hint: "A mechanic comes to the car" },
  { value: "tow", label: "Tow the car", hint: "To a workshop" },
  { value: "workshop", label: "Workshop visit", hint: "I'll bring the car in" },
];

// Same rules as the API (backend/app/requests/schemas.py).
const MOBILE = /^(?:\+?91|0)?[6-9]\d{9}$/;
const PINCODE = /^[1-9]\d{5}$/;

interface Errors {
  name?: string;
  phone?: string;
  service?: string;
  area?: string;
  pincode?: string;
  consent?: string;
}

/** Emergency: a fast-track topic or a red safety alert (the API decides the same way). */
export function isUrgent(result: ResultOut | null): boolean {
  return !!result && (result.mode === "fast_track" || result.safety_alerts.length > 0);
}

function Helpline({ number, urgent }: { number: string; urgent: boolean }) {
  if (!number) return null;
  return (
    <div
      className={
        urgent
          ? "flex flex-col gap-2 rounded-3xl bg-ink p-5 text-white sm:flex-row sm:items-center sm:justify-between"
          : "rounded-2xl border border-border bg-white p-4 text-ink"
      }
      data-testid="helpline"
    >
      <p className="flex items-center gap-2 text-lg font-bold">
        <Phone aria-hidden="true" className="size-5 shrink-0" />
        {urgent ? "Emergency? Call our helpline now:" : "Helpline:"}{" "}
        <span className="tracking-wide whitespace-nowrap">{number}</span>
      </p>
      {urgent && (
        <a
          href={`tel:${number.replace(/[^\d+]/g, "")}`}
          className="inline-flex min-h-12 shrink-0 items-center justify-center rounded-full bg-white px-6 text-lg font-bold whitespace-nowrap text-ink outline-none focus-visible:ring-3 focus-visible:ring-white/70"
        >
          Call now
        </a>
      )}
    </div>
  );
}

function Summary({ result }: { result: ResultOut }) {
  const top = result.ranked[0];
  return (
    <section aria-labelledby="summary-heading" className="rounded-3xl border border-border bg-white p-5">
      <h2 id="summary-heading" className="text-sm font-bold tracking-wide text-ink/70 uppercase">
        Sent with your request
      </h2>
      <p className="mt-2 flex items-center gap-2 font-bold text-ink" data-testid="request-car">
        <CarFront aria-hidden="true" className="size-5 shrink-0 text-orange-text" />
        {result.vehicle.label}
      </p>
      <p className="mt-1 text-ink/80" data-testid="request-diagnosis">
        {[result.topic, top ? `Likely cause: ${top.name}` : null].filter(Boolean).join(" · ") || "Your diagnosis"}
      </p>
    </section>
  );
}

function Confirmation({ out, sessionId }: { out: ServiceRequestOut; sessionId: string | null }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []); // announce the reference to screen readers
  return (
    <section aria-labelledby="done-heading" className="flex flex-col gap-5" data-testid="confirmation">
      <div className="rounded-3xl border-2 border-cta bg-white p-6">
        <p className="flex items-center gap-2 font-bold text-orange-text">
          <CircleCheck aria-hidden="true" className="size-6" />
          Request sent{out.urgent ? " (urgent)" : ""}
        </p>
        <h1 id="done-heading" ref={heading} tabIndex={-1} className="mt-2 text-3xl outline-none font-black tracking-tight text-ink sm:text-4xl">
          Your reference is{" "}
          <span className="tracking-wider whitespace-nowrap text-orange-text" data-testid="reference">
            {out.reference}
          </span>
        </h1>
      </div>
      <section aria-labelledby="next-heading" className="rounded-3xl border border-border bg-white p-5">
        <h2 id="next-heading" className="text-xl font-black text-ink">
          What happens next
        </h2>
        <ol className="mt-2 flex list-decimal flex-col gap-1.5 pl-5 text-ink/90">
          {out.next_steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      </section>
      <AlertsButton />
      {out.helpline_number && (
        <p className="rounded-2xl bg-white p-4 text-lg text-ink">
          Helpline: <span className="font-bold tracking-wide">{out.helpline_number}</span>
        </p>
      )}
      <div className="flex flex-col gap-3 sm:flex-row">
        {sessionId && (
          <Button asChild size="cta" variant="outline" className="border-2 border-ink/15 bg-white text-ink">
            <Link href={`/diagnose/${sessionId}/result`}>Back to your result</Link>
          </Button>
        )}
        <Button asChild size="cta" variant="outline" className="border-2 border-ink/15 bg-white text-ink">
          <Link href="/">Home</Link>
        </Button>
      </div>
    </section>
  );
}

function Form({
  config,
  result,
  sessionId,
  onSent,
}: {
  config: RequestConfig;
  result: ResultOut | null;
  sessionId: string | null;
  onSent: (out: ServiceRequestOut) => void;
}) {
  const consentId = useId();
  const urgent = isUrgent(result);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [service, setService] = useState<ServiceType | undefined>(urgent ? "at_location" : undefined);
  const [area, setArea] = useState("");
  const [pincode, setPincode] = useState("");
  const [address, setAddress] = useState("");
  const [time, setTime] = useState<string | undefined>();
  const [notes, setNotes] = useState("");
  const [consent, setConsent] = useState(false);
  const [whatsapp, setWhatsapp] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const digits = phone.replace(/[\s().-]/g, "");
    const next: Errors = {
      name: name.trim().length >= 2 ? undefined : "Type your name.",
      phone: MOBILE.test(digits) ? undefined : "Enter a 10-digit Indian mobile number starting with 6, 7, 8 or 9.",
      service: service ? undefined : "Choose how we should help.",
      area: area.trim().length >= 2 ? undefined : "Type your area, sector or a landmark.",
      pincode:
        pincode.trim() ? (PINCODE.test(pincode.trim()) ? undefined : "Enter a 6-digit pincode.") : urgent ? undefined : "Enter a 6-digit pincode.",
      consent: consent ? undefined : "Tick the box so we can share your details with our team.",
    };
    setErrors(next);
    if (Object.values(next).some(Boolean)) {
      const form = e.currentTarget as HTMLFormElement;
      requestAnimationFrame(() =>
        form.querySelector<HTMLElement>('[aria-invalid="true"], fieldset[aria-describedby] input')?.focus(),
      );
      return;
    }
    setSending(true);
    setError(null);
    try {
      onSent(
        await api.createRequest({
          session_id: sessionId,
          name: name.trim(),
          phone,
          service_type: service!,
          area: area.trim(),
          pincode: pincode.trim(),
          address: urgent ? "" : address.trim(),
          preferred_time: urgent ? "" : (time ?? ""),
          notes: urgent ? "" : notes.trim(),
          consent,
          consent_text_version: config.consent_version,
          whatsapp_optin: whatsapp,
          whatsapp_consent_version: whatsapp ? config.whatsapp_consent_version : null,
        }),
      );
    } catch (err) {
      setError(errorMessage(err));
      setSending(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-6" aria-labelledby="request-heading">
      <div>
        <h1 id="request-heading" className="text-4xl leading-tight font-black tracking-tight text-ink sm:text-5xl">
          {urgent ? "Get help now" : "Request a Mechanic"}
        </h1>
        <p className="mt-2 text-lg text-ink/75">
          {urgent
            ? "Just your name, number and where you are. We'll call you back first."
            : "Tell us how to reach you. Our team will call to confirm before anything is booked."}
        </p>
      </div>
      <Helpline number={config.helpline_number} urgent={urgent} />
      {result && <Summary result={result} />}

      <div className="grid gap-5 sm:grid-cols-2">
        <TextField label="Your name" value={name} onChange={setName} error={errors.name} autoComplete="name" maxLength={80} />
        <TextField
          label="Mobile number"
          value={phone}
          onChange={setPhone}
          error={errors.phone}
          type="tel"
          inputMode="tel"
          autoComplete="tel-national"
          placeholder="98765 43210"
          maxLength={16}
        />
      </div>
      <ChoiceGroup
        legend="How should we help?"
        choices={SERVICE_TYPES}
        value={service}
        onChange={setService}
        columns="grid-cols-1 sm:grid-cols-3"
        error={errors.service}
      />
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField
          label="Area, sector or landmark"
          value={area}
          onChange={setArea}
          error={errors.area}
          autoComplete="address-level3"
          maxLength={120}
          placeholder="e.g. Sector 62, Noida"
        />
        <TextField
          label={urgent ? "Pincode (optional)" : "Pincode"}
          value={pincode}
          onChange={setPincode}
          error={errors.pincode}
          inputMode="numeric"
          autoComplete="postal-code"
          maxLength={6}
        />
      </div>

      {!urgent && (
        <>
          <TextField label="Address (optional)" value={address} onChange={setAddress} autoComplete="street-address" maxLength={300} />
          <ChoiceGroup
            legend="Preferred time (optional)"
            choices={config.preferred_times}
            value={time}
            onChange={setTime}
            columns="grid-cols-1 sm:grid-cols-2"
          />
          <div className="flex flex-col gap-2">
            <label htmlFor={`${consentId}-notes`} className="text-lg font-bold text-ink">
              Notes (optional)
            </label>
            <textarea
              id={`${consentId}-notes`}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={500}
              rows={3}
              placeholder="e.g. car is in the basement parking"
              className="rounded-3xl border-2 border-ink/15 bg-white p-4 text-lg text-ink outline-none focus-visible:border-cta focus-visible:ring-3 focus-visible:ring-ring/40"
            />
          </div>
        </>
      )}

      <div className="flex flex-col gap-2">
        {/* The whole row is the label: tapping anywhere on it ticks the box (a target well over 44px). */}
        <label
          htmlFor={consentId}
          className="flex min-h-14 cursor-pointer items-start gap-3 rounded-2xl border-2 border-ink/15 bg-white p-4 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring"
        >
          <input
            id={consentId}
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            aria-invalid={errors.consent ? true : undefined}
            aria-describedby={errors.consent ? `${consentId}-error` : undefined}
            className="mt-0.5 size-6 shrink-0 accent-cta outline-none"
          />
          <span className="text-ink" data-testid="consent-text">
            {config.consent_text}
          </span>
        </label>
        {errors.consent && (
          <p id={`${consentId}-error`} className="text-sm font-semibold text-orange-text">
            {errors.consent}
          </p>
        )}
      </div>

      {/* Optional and separate from the consent above: WhatsApp updates need their own opt-in (stored with this
          wording and its version). Unticked by default. */}
      {config.whatsapp_consent_text && (
        <label
          htmlFor={`${consentId}-whatsapp`}
          className="flex min-h-14 cursor-pointer items-start gap-3 rounded-2xl border-2 border-ink/15 bg-white p-4 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring"
        >
          <input
            id={`${consentId}-whatsapp`}
            type="checkbox"
            checked={whatsapp}
            onChange={(e) => setWhatsapp(e.target.checked)}
            className="mt-0.5 size-6 shrink-0 accent-cta outline-none"
          />
          <span className="text-ink" data-testid="whatsapp-consent-text">
            <span className="font-bold">Optional: </span>
            {config.whatsapp_consent_text}
          </span>
        </label>
      )}

      {error && <ErrorMessage message={error} />}
      <Button type="submit" size="cta" disabled={sending} className="self-stretch sm:self-start">
        {sending && <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />}
        {urgent ? "Send urgent request" : "Request a Mechanic"}
      </Button>
      <p className="text-sm text-ink/70">We only use your details for this request.</p>
    </form>
  );
}

/** /request?session=…: the form prefilled from the diagnosis, then the confirmation with the reference. */
export function RequestForm({ sessionId }: { sessionId: string | null }) {
  const config = useLoad("request-config", (signal) => api.requestConfig(signal));
  const result = useLoad(sessionId ? `result:${sessionId}` : null, (signal) => api.result(sessionId!, signal));
  const [sent, setSent] = useState<ServiceRequestOut | null>(null);

  if (sent) return <Confirmation out={sent} sessionId={sessionId} />;
  const resultReady = !sessionId || result.state.status === "ready";
  if (config.state.status === "loading" || (sessionId && result.state.status === "loading")) {
    return (
      <div className="flex flex-col gap-5" aria-busy="true">
        <span role="status" className="sr-only">
          Loading the request form…
        </span>
        <Skeleton className="h-12 w-2/3" />
        <Skeleton className="h-28 rounded-3xl" />
        <Skeleton className="h-56 rounded-3xl" />
      </div>
    );
  }
  if (config.state.status === "error") return <ErrorMessage message={config.state.message} onRetry={config.retry} />;
  return (
    <>
      {sessionId && result.state.status === "error" && (
        <p className="mb-4 rounded-2xl bg-white p-4 text-ink/80">
          We couldn&apos;t load your diagnosis, but you can still send the request.
        </p>
      )}
      <Form
        config={config.state.data}
        result={resultReady && result.state.status === "ready" ? result.state.data : null}
        sessionId={sessionId && result.state.status === "ready" ? sessionId : null}
        onSent={(out) => {
          setSent(out);
          window.scrollTo({ top: 0 });
        }}
      />
    </>
  );
}
