"use client";

import { NextIntlClientProvider, useTranslations } from "next-intl";
import { createContext, useCallback, useContext, useSyncExternalStore, type ReactNode } from "react";

import { TIME_ZONE } from "@/i18n/config";
import en from "@/i18n/messages/m.en.json";
import hi from "@/i18n/messages/m.hi.json";

// The mechanic app speaks Hindi first (English on the Profile page switch). Short, plain words.
// Phase 5.5: one i18n approach for the whole web app. The texts are in src/i18n/messages/m.{hi,en}.json and are
// served by next-intl, like the customer pages; the mechanic's choice stays in localStorage (no /hi URLs here).
export type Lang = "hi" | "en";
const KEY = "im_m_lang";

const MESSAGES = { hi, en } as const;

type Key = Exclude<keyof typeof en.m, "statusNames">;

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "hi", setLang: () => undefined });

// The choice is kept in localStorage; the server (and the first paint) uses Hindi.
const listeners = new Set<() => void>();
let fallback: Lang = "hi"; // when localStorage is not available (private mode)

function readLang(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "en" || saved === "hi" ? saved : fallback;
  } catch {
    return fallback;
  }
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function LangProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore(subscribe, readLang, () => "hi" as Lang);
  const setLang = useCallback((l: Lang) => {
    fallback = l;
    try {
      localStorage.setItem(KEY, l);
    } catch {
      // not remembered after a reload
    }
    listeners.forEach((cb) => cb());
  }, []);
  return (
    <Ctx.Provider value={{ lang, setLang }}>
      <NextIntlClientProvider locale={lang} messages={MESSAGES[lang]} timeZone={TIME_ZONE}>
        <div lang={lang === "hi" ? "hi" : "en"} className="contents">
          {children}
        </div>
      </NextIntlClientProvider>
    </Ctx.Provider>
  );
}

export function useLang() {
  return useContext(Ctx);
}

export function useT() {
  const t = useTranslations("m");
  return useCallback((key: Key, vars?: Record<string, string | number>) => t(key, vars), [t]);
}

export function useStatusName() {
  const t = useTranslations("m.statusNames");
  return (status: string) => (t.has(status as never) ? t(status as never) : status);
}
