"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { Copy, ShieldCheck } from "lucide-react";

import { Button } from "@im/ui/button";
import { Field } from "@/components/field";
import { adminApi, errorMessage, type TwoFactorSetup } from "@/lib/api";

type Step = { kind: "password" } | { kind: "code" } | { kind: "setup"; setup: TwoFactorSetup };

/** Where to go after signing in: a path on this site from ?next=, else the overview. */
export function safeNext(search: string): string {
  const next = new URLSearchParams(search).get("next") ?? "/";
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}

export function groupKey(secret: string): string {
  return secret.replace(/(.{4})/g, "$1 ").trim();
}

/** Staff sign-in: email + password, then the authenticator code. An account without two-factor (new staff, or
 * after a reset) gets the setup step: the QR code and key are shown once, then a code finishes it. */
export function LoginView() {
  const router = useRouter();
  const [step, setStep] = useState<Step>({ kind: "password" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  // Kept in memory between the password and code steps only (never stored).
  const creds = useRef({ email: "", password: "" });

  function signedIn() {
    router.replace(safeNext(window.location.search));
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function submitPassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    creds.current = { email: String(f.get("email")).trim(), password: String(f.get("password")) };
    void run(async () => {
      const r = await adminApi.login(creds.current.email, creds.current.password);
      if (r.next === "done") return signedIn();
      setStep(r.next === "setup" && r.setup ? { kind: "setup", setup: r.setup } : { kind: "code" });
    });
  }

  function submitCode(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code")).replace(/\s/g, "");
    void run(async () => {
      if (step.kind === "setup") {
        await adminApi.confirmTwoFactor(code);
        creds.current = { email: "", password: "" };
        return signedIn();
      }
      const r = await adminApi.login(creds.current.email, creds.current.password, code);
      if (r.next !== "done") throw new Error("Please sign in again.");
      creds.current = { email: "", password: "" };
      signedIn();
    });
  }

  function startOver() {
    creds.current = { email: "", password: "" };
    setError("");
    setStep({ kind: "password" });
  }

  const errorLine = error && (
    <p role="alert" className="font-semibold text-orange-text">
      {error}
    </p>
  );
  const codeField = (
    <Field
      label="6-digit code from your authenticator app"
      name="code"
      inputMode="numeric"
      autoComplete="one-time-code"
      pattern="[0-9 ]{6,7}"
      maxLength={7}
      required
      autoFocus
    />
  );

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 p-4 py-10">
      <p className="text-2xl font-black tracking-tight text-ink">
        Instant <span className="text-orange-text">Mechanic</span>
        <span className="ml-2 rounded-full bg-ink px-2 py-0.5 align-middle text-xs font-bold text-white">Admin</span>
      </p>

      {step.kind === "password" && (
        <form onSubmit={submitPassword} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-6">
          <h1 className="text-3xl font-black text-ink">Staff sign in</h1>
          <Field label="Email" name="email" type="email" autoComplete="username" required autoFocus />
          <Field label="Password" name="password" type="password" autoComplete="current-password" required />
          {errorLine}
          <Button type="submit" size="cta" disabled={busy}>
            {busy ? "Checking…" : "Continue"}
          </Button>
          <p className="text-sm text-ink/70">Customers sign in on the website, not here.</p>
        </form>
      )}

      {step.kind === "code" && (
        <form onSubmit={submitCode} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-6">
          <h1 className="text-3xl font-black text-ink">Two-factor code</h1>
          <p className="text-ink/80">Open your authenticator app and type the code for Instant Mechanic.</p>
          {codeField}
          {errorLine}
          <Button type="submit" size="cta" disabled={busy}>
            {busy ? "Checking…" : "Sign in"}
          </Button>
          <button type="button" onClick={startOver} className="min-h-11 self-start font-bold text-orange-text underline underline-offset-4">
            Use another account
          </button>
        </form>
      )}

      {step.kind === "setup" && (
        <form onSubmit={submitCode} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-6" data-testid="two-factor-setup">
          <h1 className="flex items-center gap-2 text-3xl font-black text-ink">
            <ShieldCheck aria-hidden="true" className="size-7 text-orange-text" />
            Set up two-factor
          </h1>
          <ol className="flex list-decimal flex-col gap-2 pl-5 text-ink">
            <li>Install Google Authenticator (or another authenticator app) on your phone.</li>
            <li>
              In the app tap <strong>+</strong>, then <strong>Scan a QR code</strong>, and scan this code:
            </li>
          </ol>
          {/* eslint-disable-next-line @next/next/no-img-element -- an SVG made by our API, shown once */}
          <img
            src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(step.setup.qr_svg)}`}
            alt="QR code to add Instant Mechanic to your authenticator app"
            width={224}
            height={224}
            className="self-center rounded-xl border border-border bg-white p-2"
          />
          <div className="rounded-2xl bg-warm-white p-3">
            <p className="text-sm text-ink/80">Can&apos;t scan? Choose <strong>Enter a setup key</strong> and type:</p>
            <p className="mt-1 flex flex-wrap items-center gap-2">
              <code className="font-mono text-lg font-bold tracking-wider break-all text-ink" data-testid="setup-key">
                {groupKey(step.setup.secret)}
              </code>
              <button
                type="button"
                onClick={() => void navigator.clipboard?.writeText(step.setup.secret).then(() => setCopied(true))}
                className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 font-semibold text-orange-text outline-none hover:bg-white focus-visible:ring-3 focus-visible:ring-ring"
              >
                <Copy aria-hidden="true" className="size-4" />
                {copied ? "Copied" : "Copy"}
              </button>
            </p>
            <p className="mt-1 text-sm text-ink/70">Time based, 6 digits. This QR code and key are shown only now.</p>
          </div>
          <p className="text-ink">3. Type the code the app shows to finish:</p>
          {codeField}
          {errorLine}
          <Button type="submit" size="cta" disabled={busy}>
            {busy ? "Checking…" : "Finish and sign in"}
          </Button>
          <button type="button" onClick={startOver} className="min-h-11 self-start font-bold text-orange-text underline underline-offset-4">
            Start again
          </button>
        </form>
      )}
    </main>
  );
}
