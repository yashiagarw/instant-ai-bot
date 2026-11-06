"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Car, LoaderCircle, MapPin, ShieldAlert, Timer, Wrench } from "lucide-react";

import { useT } from "@/components/m/i18n";
import { PRIMARY, SECONDARY, useMe } from "@/components/m/shell";
import { mechanicApi, MechanicApiError, type Offer } from "@/lib/mechanic-api";

const POLL_MS = 15_000; // while the page is visible; small answers, fine on slow 4G

/** Open offers: job type, car, diagnosis summary and the approximate area only, with the time left to answer. */
export function OffersView() {
  const t = useT();
  const router = useRouter();
  const { refresh } = useMe();
  const [offers, setOffers] = useState<Offer[] | null>(null);
  const [loadedAt, setLoadedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      mechanicApi
        .offers()
        .then((o) => {
          setOffers(o);
          setLoadedAt(Date.now());
          setError(null);
        })
        .catch((e) => setError(e instanceof MechanicApiError && e.status === 0 ? t("offline") : t("error"))),
    [t],
  );

  useEffect(() => {
    void load();
    const poll = setInterval(() => document.visibilityState === "visible" && void load(), POLL_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const back = () => document.visibilityState === "visible" && void load();
    document.addEventListener("visibilitychange", back);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
      document.removeEventListener("visibilitychange", back);
    };
  }, [load]);

  async function answer(o: Offer, accept: boolean) {
    setBusy(o.id);
    setError(null);
    try {
      if (accept) {
        const job = await mechanicApi.accept(o.id);
        await refresh();
        router.push(`/m/jobs/${job.id}`);
        return;
      }
      await mechanicApi.reject(o.id);
      await Promise.all([load(), refresh()]);
    } catch (e) {
      await load(); // the list as it is now, then why it did not work
      setError(
        e instanceof MechanicApiError && e.status === 409 ? t("offerGone") : e instanceof MechanicApiError && e.status === 0 ? t("offline") : t("error"),
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <h1 className="text-3xl font-black">{t("offers")}</h1>
      {error && (
        <p role="alert" className="rounded-2xl bg-white p-3 text-lg font-bold text-danger">
          {error}
        </p>
      )}
      {offers === null && !error && <p className="text-lg">{t("loading")}</p>}
      {offers?.length === 0 && <p className="text-lg">{t("noOffers")}</p>}
      <ul className="flex flex-col gap-4" data-testid="offers">
        {offers?.map((o) => {
          const left = o.seconds_left === null ? null : Math.max(0, o.seconds_left - Math.floor((now - loadedAt) / 1000));
          const gone = left === 0;
          return (
            <li key={o.id} className="flex flex-col gap-3 rounded-3xl border-2 border-ink bg-white p-4" data-testid="offer">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xl font-black tabular-nums">{o.reference}</span>
                {left !== null && (
                  <span
                    className={`flex items-center gap-1 rounded-full px-3 py-1 text-lg font-black tabular-nums ${gone ? "bg-ink/10" : "bg-amber-bg text-amber-text"}`}
                    aria-live="off"
                  >
                    <Timer aria-hidden="true" className="size-5" />
                    {gone ? t("expired") : `${left} ${t("secondsLeft")}`}
                  </span>
                )}
              </div>
              {(o.urgent || o.safety_critical) && (
                <p className="flex items-start gap-2 rounded-2xl bg-danger p-3 text-lg font-bold text-white">
                  <ShieldAlert aria-hidden="true" className="mt-0.5 size-6 shrink-0" />
                  {o.safety_critical ? t("safety") : t("urgent")}
                </p>
              )}
              <dl className="grid gap-2 text-lg">
                <Row icon={<Wrench aria-hidden="true" className="size-6" />} label={t("jobType")} value={o.job_type_label} />
                <Row icon={<Car aria-hidden="true" className="size-6" />} label={t("car")} value={o.car} />
                <Row label={t("problem")} value={o.problem} />
                <Row
                  icon={<MapPin aria-hidden="true" className="size-6" />}
                  label={t("approxArea")}
                  value={o.area + (o.distance_km !== null ? ` · ${t("approxKm", { n: o.distance_km })}` : "")}
                />
              </dl>
              <p className="text-base text-ink/80">{t("addressAfterAccept")}</p>
              <div className="grid grid-cols-2 gap-3">
                <button type="button" className={SECONDARY} disabled={busy !== null || gone} onClick={() => answer(o, false)}>
                  {t("reject")}
                </button>
                <button type="button" className={PRIMARY} disabled={busy !== null || gone} onClick={() => answer(o, true)}>
                  {busy === o.id && <LoaderCircle aria-hidden="true" className="size-6 animate-spin motion-reduce:animate-none" />}
                  {t("accept")}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function Row({ icon, label, value }: { icon?: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 w-6 shrink-0">{icon}</span>
      <div>
        <dt className="text-base font-bold text-ink/70">{label}</dt>
        <dd className="font-semibold">{value}</dd>
      </div>
    </div>
  );
}
