"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Cloudflare Turnstile ("I'm human" check) on public forms: the request form and the sign-in code requests.
// NEXT_PUBLIC_TURNSTILE_SITE_KEY empty = no widget and no token (the API's check is off without its secret too).
// Development and tests use Cloudflare's test site key 1x00000000000000000000AA (always passes, no puzzle).
const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";
const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

type TurnstileApi = {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  reset: (id: string) => void;
  remove: (id: string) => void;
};
declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loading: Promise<TurnstileApi | null> | null = null;

function load(): Promise<TurnstileApi | null> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  loading ??= new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = SCRIPT;
    s.async = true;
    s.onload = () => resolve(window.turnstile ?? null);
    s.onerror = () => {
      loading = null;
      resolve(null);
    };
    document.head.appendChild(s);
  });
  return loading;
}

/**
 * The widget and its token. `required` is false when Turnstile is not configured (submit without a token).
 * Tokens work once: call reset() after each submit.
 */
export function useHumanCheck(lang = "en") {
  const ref = useRef<HTMLDivElement | null>(null);
  const widget = useRef<string | null>(null);
  const [token, setToken] = useState<string | undefined>(undefined);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!SITE_KEY || !ref.current) return;
    let cancelled = false;
    const el = ref.current;
    load().then((api) => {
      if (cancelled) return;
      if (!api) return setFailed(true);
      widget.current = api.render(el, {
        sitekey: SITE_KEY,
        size: "flexible",
        language: lang,
        callback: (t: string) => {
          setToken(t);
          setFailed(false);
        },
        "expired-callback": () => setToken(undefined),
        "error-callback": () => setFailed(true),
      });
    });
    return () => {
      cancelled = true;
      if (widget.current && window.turnstile) window.turnstile.remove(widget.current);
      widget.current = null;
    };
  }, [lang]);

  const reset = useCallback(() => {
    setToken(undefined);
    if (widget.current && window.turnstile) window.turnstile.reset(widget.current);
  }, []);

  const box = SITE_KEY ? (
    <div className="flex flex-col gap-1">
      <div ref={ref} data-testid="human-check" className="min-h-16" />
      {failed && (
        <p role="alert" className="text-sm font-semibold text-orange-text">
          The &quot;I&apos;m human&quot; check didn&apos;t load. Check your connection and reload the page.
        </p>
      )}
    </div>
  ) : null;

  return { box, token, required: Boolean(SITE_KEY), reset };
}
