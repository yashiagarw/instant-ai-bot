"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { ErrorMessage } from "@/components/error-message";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { useHumanCheck } from "@/components/turnstile";
import { accountApi, errorMessage } from "@/lib/api";
import { useLoad } from "@/lib/use-load";

const RESEND_AFTER = 30;

/** Where to go after login: a path on this site only (never another origin). */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/account";
}

/** Log in with a mobile number and a 6-digit SMS code. Diagnoses and requests made in this browser join the account. */
export function LoginView() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const config = useLoad("auth-config", (signal) => accountApi.config(signal));
  const id = useId();
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [consent, setConsent] = useState(false);
  const [masked, setMasked] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(0);
  const human = useHumanCheck();

  useEffect(() => {
    if (wait <= 0) return;
    const t = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);

  async function sendCode() {
    if (!/^[6-9]\d{9}$/.test(phone)) {
      setError("Enter your 10-digit mobile number");
      return;
    }
    if (human.required && !human.token) {
      setError('Please complete the "I\'m human" check first');
      return;
    }
    setBusy(true);
    setError("");
    try {
      const r = await accountApi.requestCode(phone, human.token);
      setMasked(r.phone_masked);
      setStep("code");
      setCode("");
      setWait(RESEND_AFTER);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      human.reset(); // a token works once
      setBusy(false);
    }
  }

  async function verify(consentVersion: string) {
    if (!/^\d{6}$/.test(code)) {
      setError("Enter the 6-digit code from the SMS");
      return;
    }
    if (!consent) {
      setError("Please tick the box to agree before logging in");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await accountApi.verifyCode(phone, code, consentVersion);
      router.push(next);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  if (config.state.status === "loading") return <Skeleton className="h-80 rounded-3xl" />;
  if (config.state.status === "error") return <ErrorMessage message={config.state.message} onRetry={config.retry} />;
  const cfg = config.state.data;

  return (
    <section aria-labelledby={`${id}-h`} className="flex flex-col gap-5 rounded-3xl border border-border bg-white p-5 sm:p-7">
      <div>
        <h1 id={`${id}-h`} className="text-3xl leading-tight font-black tracking-tight text-ink">
          Log in
        </h1>
        <p className="mt-2 text-ink/80">
          See your saved cars, past diagnoses and mechanic requests. Diagnoses you made on this device are added to
          your account.
        </p>
      </div>

      {/* Above both steps, so "Send a new code" can use it too. */}
      {human.box}
      {step === "phone" ? (
        <form method="post"
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void sendCode();
          }}
        >
          <div className="flex flex-col gap-2">
            <label htmlFor={`${id}-phone`} className="text-lg font-bold text-ink">
              Mobile number
            </label>
            <div className="flex h-14 items-center rounded-full border-2 border-ink/15 bg-white focus-within:border-cta focus-within:ring-3 focus-within:ring-ring/40">
              <span className="pl-5 text-lg font-semibold text-ink/70" aria-hidden="true">
                +91
              </span>
              <input
                id={`${id}-phone`}
                type="tel"
                inputMode="numeric"
                autoComplete="tel-national"
                maxLength={10}
                value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? `${id}-error` : `${id}-hint`}
                className="h-full w-full rounded-r-full bg-transparent px-3 text-lg text-ink tabular-nums outline-none"
              />
            </div>
            <p id={`${id}-hint`} className="text-sm text-ink/70">
              We send a 6-digit code by SMS.
            </p>
          </div>
          {error && (
            <p id={`${id}-error`} role="alert" className="font-semibold text-orange-text">
              {error}
            </p>
          )}
          <Button type="submit" size="cta" disabled={busy} className="w-full sm:w-auto">
            {busy ? "Sending…" : "Send code"}
          </Button>
        </form>
      ) : (
        <form method="post"
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void verify(cfg.consent_version);
          }}
        >
          <p className="text-ink" aria-live="polite">
            We sent a code to <span className="font-bold tabular-nums">{masked}</span>. It works for{" "}
            {Math.round(cfg.expires_in / 60)} minutes.
          </p>
          <div className="flex flex-col gap-2">
            <label htmlFor={`${id}-code`} className="text-lg font-bold text-ink">
              6-digit code
            </label>
            <input
              id={`${id}-code`}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${id}-error` : undefined}
              className="h-14 w-48 rounded-full border-2 border-ink/15 bg-white px-5 text-2xl tracking-[0.3em] text-ink tabular-nums outline-none focus-visible:border-cta focus-visible:ring-3 focus-visible:ring-ring/40"
            />
          </div>
          <label className="flex cursor-pointer items-start gap-3 rounded-2xl bg-warm-white p-4 text-ink">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="mt-1 size-5 shrink-0 accent-cta"
            />
            <span>{cfg.consent_text}</span>
          </label>
          {error && (
            <p id={`${id}-error`} role="alert" className="font-semibold text-orange-text">
              {error}
            </p>
          )}
          <Button type="submit" size="cta" disabled={busy} className="w-full sm:w-auto">
            {busy ? "Checking…" : "Log in"}
          </Button>
          <div className="flex flex-wrap gap-x-5">
            <button
              type="button"
              disabled={wait > 0 || busy}
              onClick={() => void sendCode()}
              className="min-h-11 rounded-full font-bold text-orange-text underline underline-offset-4 outline-none disabled:text-ink/50 disabled:no-underline focus-visible:ring-3 focus-visible:ring-ring"
            >
              {wait > 0 ? `Send a new code in ${wait}s` : "Send a new code"}
            </button>
            <button
              type="button"
              onClick={() => {
                setStep("phone");
                setError("");
              }}
              className="min-h-11 rounded-full font-bold text-orange-text underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
            >
              Change number
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
