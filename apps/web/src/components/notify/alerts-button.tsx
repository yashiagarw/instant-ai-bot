"use client";

import { useEffect, useRef, useState } from "react";
import { BellOff, BellRing, LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { notifyApi } from "@/lib/api";

type State = "checking" | "unavailable" | "unsupported" | "denied" | "off" | "busy" | "on";

/** The VAPID public key (base64url) as the bytes PushManager.subscribe wants. */
export function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

function supported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration("/");
  return (await reg?.pushManager.getSubscription()) ?? null;
}

/**
 * "Turn on alerts": browser notifications when the mechanic is assigned, on the way, has arrived and is done.
 * Hidden when the server has no push key; explains itself when the browser can't (or the person blocked it).
 */
export function AlertsButton({ onChange }: { onChange?: (on: boolean) => void }) {
  const [state, setState] = useState<State>("checking");
  const [error, setError] = useState<string | null>(null);
  const key = useRef<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    (async () => {
      const cfg = await notifyApi.config(ctrl.signal).catch(() => null);
      if (ctrl.signal.aborted) return;
      if (!cfg?.push_public_key) return setState("unavailable");
      key.current = cfg.push_public_key;
      if (!supported()) return setState("unsupported");
      if (Notification.permission === "denied") return setState("denied");
      setState((await currentSubscription().catch(() => null)) ? "on" : "off");
    })();
    return () => ctrl.abort();
  }, []);

  async function turnOn() {
    setState("busy");
    setError(null);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState(permission === "denied" ? "denied" : "off");
        return;
      }
      const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      await navigator.serviceWorker.ready;
      const sub =
        (await reg.pushManager.getSubscription()) ??
        (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key.current!) }));
      const json = sub.toJSON();
      await notifyApi.subscribe({ endpoint: sub.endpoint, keys: { p256dh: json.keys!.p256dh, auth: json.keys!.auth } });
      setState("on");
      onChange?.(true);
    } catch {
      setError("We couldn't turn alerts on. Please try again.");
      setState("off");
    }
  }

  async function turnOff() {
    setState("busy");
    setError(null);
    try {
      const sub = await currentSubscription();
      if (sub) {
        await notifyApi.unsubscribe(sub.endpoint).catch(() => undefined);
        await sub.unsubscribe();
      }
      setState("off");
      onChange?.(false);
    } catch {
      setError("We couldn't turn alerts off. Please try again.");
      setState("on");
    }
  }

  if (state === "checking" || state === "unavailable") return null;
  return (
    <div className="flex flex-col gap-2 rounded-3xl border border-border bg-white p-5" data-testid="alerts">
      <h2 className="text-xl font-black text-ink">Alerts on this phone</h2>
      {state === "unsupported" && (
        <p className="text-ink/80">
          This browser can&apos;t show alerts. On an iPhone, add this site to your Home Screen first, then open it from there.
        </p>
      )}
      {state === "denied" && (
        <p className="flex items-start gap-2 text-ink/80">
          <BellOff aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
          Alerts are blocked for this site. Allow notifications in your browser&apos;s site settings, then reload.
        </p>
      )}
      {(state === "off" || state === "busy") && (
        <>
          <p className="text-ink/80">Get an alert when your mechanic is assigned, on the way, has arrived and is done.</p>
          <Button type="button" size="cta" onClick={turnOn} disabled={state === "busy"} className="self-stretch sm:self-start">
            {state === "busy" ? (
              <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
            ) : (
              <BellRing aria-hidden="true" className="size-5" />
            )}
            Turn on alerts
          </Button>
        </>
      )}
      {state === "on" && (
        <div className="flex flex-wrap items-center gap-3">
          <p role="status" className="flex items-center gap-2 font-bold text-orange-text">
            <BellRing aria-hidden="true" className="size-5" />
            Alerts are on for this browser
          </p>
          <button
            type="button"
            onClick={turnOff}
            className="min-h-11 font-bold text-ink underline underline-offset-4"
          >
            Turn off
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm font-semibold text-orange-text">
          {error}
        </p>
      )}
    </div>
  );
}
