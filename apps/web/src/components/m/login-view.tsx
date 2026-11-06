"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { LoaderCircle } from "lucide-react";

import { LangProvider, useLang, useT } from "@/components/m/i18n";
import { PRIMARY } from "@/components/m/shell";
import { mechanicApi, MechanicApiError } from "@/lib/mechanic-api";

const MOBILE = /^(?:\+?91|0)?[6-9]\d{9}$/;

export function MechanicLoginView() {
  return (
    <LangProvider>
      <Login />
    </LangProvider>
  );
}

function Login() {
  const t = useT();
  const { lang, setLang } = useLang();
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function message(e: unknown): string {
    if (e instanceof MechanicApiError) {
      if (e.status === 0) return t("offline");
      if (e.message) return e.message;
    }
    return t("error");
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!MOBILE.test(phone.replace(/[\s-]/g, ""))) return setError(t("badPhone"));
    setBusy(true);
    setError(null);
    try {
      setSentTo((await mechanicApi.requestCode(phone)).phone_masked);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await mechanicApi.verifyCode(phone, code.trim());
      router.replace("/m");
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh flex-col bg-ink p-5 text-white">
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6">
        <div className="flex items-center justify-between">
          <p className="text-2xl font-black text-brand">{t("appName")}</p>
          <button
            type="button"
            onClick={() => setLang(lang === "hi" ? "en" : "hi")}
            className="min-h-12 rounded-full border-2 border-white/40 px-4 text-lg font-bold"
          >
            {lang === "hi" ? "English" : "हिंदी"}
          </button>
        </div>
        <h1 className="text-4xl font-black">{t("signInTitle")}</h1>
        {!sentTo ? (
          <form onSubmit={send} className="flex flex-col gap-4" noValidate>
            <p className="text-lg text-white/90">{t("signInHint")}</p>
            <label className="flex flex-col gap-2 text-lg font-bold">
              {t("mobile")}
              <input
                type="tel"
                inputMode="tel"
                autoComplete="tel-national"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="min-h-14 rounded-2xl bg-white px-4 text-2xl font-bold text-ink tabular-nums outline-none focus-visible:ring-4 focus-visible:ring-brand"
              />
            </label>
            <button type="submit" className={PRIMARY} disabled={busy}>
              {busy && <LoaderCircle aria-hidden="true" className="size-6 animate-spin motion-reduce:animate-none" />}
              {t("sendCode")}
            </button>
          </form>
        ) : (
          <form onSubmit={verify} className="flex flex-col gap-4" noValidate>
            <p className="text-lg text-white/90">
              {t("codeSent")} <span className="font-bold tabular-nums">{sentTo}</span>
            </p>
            <label className="flex flex-col gap-2 text-lg font-bold">
              {t("code")}
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                className="min-h-14 rounded-2xl bg-white px-4 text-3xl font-black tracking-[0.3em] text-ink tabular-nums outline-none focus-visible:ring-4 focus-visible:ring-brand"
              />
            </label>
            <button type="submit" className={PRIMARY} disabled={busy || code.length !== 6}>
              {busy && <LoaderCircle aria-hidden="true" className="size-6 animate-spin motion-reduce:animate-none" />}
              {t("signIn")}
            </button>
            <p className="text-base text-white/80">{t("codeHint")}</p>
          </form>
        )}
        {error && (
          <p role="alert" className="rounded-2xl bg-white p-3 text-lg font-bold text-danger">
            {error}
          </p>
        )}
      </div>
    </main>
  );
}
