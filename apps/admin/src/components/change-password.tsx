"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@im/ui/button";
import { Field } from "@/components/field";
import { adminApi, errorMessage } from "@/lib/api";

/** Your own password: the current one, a fresh authenticator code, and the new one twice. */
export function ChangePassword({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mismatch, setMismatch] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const next = String(f.get("new"));
    if (next !== String(f.get("again"))) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setBusy(true);
    setError("");
    try {
      await adminApi.changePassword(String(f.get("current")), String(f.get("code")), next);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form method="post" onSubmit={submit} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-5" noValidate>
      <Field label="Current password" name="current" type="password" autoComplete="current-password" required />
      <Field label="Code from your authenticator app" name="code" inputMode="numeric" autoComplete="one-time-code"
             pattern="[0-9]{6}" maxLength={6} required /> {/* prettier-ignore */}
      <Field label="New password" name="new" type="password" autoComplete="new-password" minLength={12} required
             hint="At least 12 characters. Not your email name." /> {/* prettier-ignore */}
      <Field label="New password again" name="again" type="password" autoComplete="new-password" required
             error={mismatch ? "The two passwords differ." : undefined} /> {/* prettier-ignore */}
      {error && (
        <p role="alert" className="font-semibold text-orange-text">
          {error}
        </p>
      )}
      <Button type="submit" size="cta" disabled={busy} className="self-start">
        {busy ? "Saving…" : "Save password"}
      </Button>
    </form>
  );
}
