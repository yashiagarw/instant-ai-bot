"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";

import { useLang, useT } from "@/components/m/i18n";
import { DutySwitch, PRIMARY, SECONDARY, useMe } from "@/components/m/shell";
import { keyBytes } from "@/components/notify/alerts-button";
import { notifyApi } from "@/lib/api";
import { mechanicApi } from "@/lib/mechanic-api";
import { getServiceWorkerRegistration, registerServiceWorker, serviceWorkerSupported } from "@/lib/service-worker";

type Alerts = "unknown" | "unavailable" | "blocked" | "off" | "on";

/** Profile: photo and name, on / off duty, language, offer alerts on this phone, sign out. */
export function ProfileView() {
  const t = useT();
  const router = useRouter();
  const { lang, setLang } = useLang();
  const { me } = useMe();
  const [alerts, setAlerts] = useState<Alerts>("unknown");
  const [key, setKey] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const cfg = await notifyApi.config().catch(() => null);
      const ok = serviceWorkerSupported() && "PushManager" in window && "Notification" in window;
      if (!cfg?.push_public_key || !ok) return setAlerts("unavailable");
      setKey(cfg.push_public_key);
      if (Notification.permission === "denied") return setAlerts("blocked");
      const reg = await getServiceWorkerRegistration();
      setAlerts((await reg?.pushManager.getSubscription()) ? "on" : "off");
    })().catch(() => setAlerts("unavailable"));
  }, []);

  async function turnOn() {
    try {
      if ((await Notification.requestPermission()) !== "granted") return setAlerts("blocked");
      const reg = await registerServiceWorker();
      if (!reg) return setAlerts("unavailable");
      await navigator.serviceWorker.ready;
      const sub =
        (await reg.pushManager.getSubscription()) ??
        (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key!) }));
      const json = sub.toJSON();
      await mechanicApi.subscribe({ endpoint: sub.endpoint, keys: { p256dh: json.keys!.p256dh, auth: json.keys!.auth } });
      setAlerts("on");
    } catch {
      setAlerts("off");
    }
  }

  return (
    <>
      <div className="flex items-center gap-4">
        {me.photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link from the private bucket
          <img src={me.photo_url} alt="" className="size-20 rounded-full object-cover" />
        ) : (
          <span aria-hidden="true" className="flex size-20 items-center justify-center rounded-full bg-ink text-3xl font-black text-white">
            {me.first_name.slice(0, 1)}
          </span>
        )}
        <div>
          <h1 className="text-3xl font-black">{me.name}</h1>
          <p className="text-lg tabular-nums">{me.phone_masked}</p>
        </div>
      </div>
      <DutySwitch />
      <section className="flex flex-col gap-3 rounded-3xl border-2 border-ink/10 bg-white p-4" aria-labelledby="lang-h">
        <h2 id="lang-h" className="text-2xl font-black">
          {t("language")}
        </h2>
        <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-labelledby="lang-h">
          {(["hi", "en"] as const).map((l) => (
            <button
              key={l}
              type="button"
              role="radio"
              aria-checked={lang === l}
              onClick={() => setLang(l)}
              className={lang === l ? PRIMARY : SECONDARY}
            >
              {l === "hi" ? "हिंदी" : "English"}
            </button>
          ))}
        </div>
      </section>
      {alerts !== "unknown" && alerts !== "unavailable" && (
        <section className="flex flex-col gap-3 rounded-3xl border-2 border-ink/10 bg-white p-4" aria-labelledby="alerts-h">
          <h2 id="alerts-h" className="text-2xl font-black">
            {t("alerts")}
          </h2>
          {alerts === "on" && (
            <p role="status" className="flex items-center gap-2 text-lg font-bold text-success">
              <BellRing aria-hidden="true" className="size-6" />
              {t("alertsOn")}
            </p>
          )}
          {alerts === "off" && (
            <button type="button" className={PRIMARY} onClick={turnOn}>
              <BellRing aria-hidden="true" className="size-6" />
              {t("turnOnAlerts")}
            </button>
          )}
          {alerts === "blocked" && <p className="text-lg">{t("alertsBlocked")}</p>}
        </section>
      )}
      <p className="rounded-3xl bg-white p-4 text-lg">{t("install")}</p>
      <button
        type="button"
        className={SECONDARY}
        onClick={async () => {
          await mechanicApi.logout().catch(() => undefined);
          router.replace("/m/login");
        }}
      >
        {t("signOut")}
      </button>
    </>
  );
}
