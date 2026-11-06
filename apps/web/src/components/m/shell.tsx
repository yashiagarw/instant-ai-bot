"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { BellRing, Home, LoaderCircle, UserRound } from "lucide-react";

import { LangProvider, useT } from "@/components/m/i18n";
import { cn } from "@/lib/utils";
import { mechanicApi, MechanicApiError, type MechanicMe } from "@/lib/mechanic-api";
import { registerServiceWorker } from "@/lib/service-worker";

type MeState = { me: MechanicMe; refresh: () => Promise<void>; setMe: (m: MechanicMe) => void };
const MeCtx = createContext<MeState | null>(null);

export function useMe(): MeState {
  const ctx = useContext(MeCtx);
  if (!ctx) throw new Error("useMe outside the mechanic shell");
  return ctx;
}

/** Big, plain, high-contrast buttons for the mechanic app (at least 56 px tall). */
export const BIG = "flex min-h-14 w-full items-center justify-center gap-2 rounded-full px-6 text-xl font-black outline-none focus-visible:ring-4 focus-visible:ring-ring disabled:opacity-60";
export const PRIMARY = cn(BIG, "bg-cta text-white");
export const SECONDARY = cn(BIG, "border-2 border-ink bg-white text-ink");

function registerWorker() {
  // The site's one service worker (/sw.js): the offline shell for /m, and offer alerts (not under `pnpm dev`).
  registerServiceWorker().catch(() => undefined);
}

/** Every signed-in page of the mechanic app: loads who they are (or sends them to sign in) and adds the tabs. */
export function MechanicShell({ children }: { children: ReactNode }) {
  return (
    <LangProvider>
      <Gate>{children}</Gate>
    </LangProvider>
  );
}

function Gate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const t = useT();
  const [me, setMe] = useState<MechanicMe | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    () =>
      mechanicApi
        .me()
        .then((m) => {
          setMe(m);
          setError(null);
        })
        .catch((e) => {
          if (e instanceof MechanicApiError && e.status === 401) router.replace("/m/login");
          else setError(e instanceof MechanicApiError && e.status === 0 ? t("offline") : t("error"));
        }),
    [router, t],
  );

  useEffect(() => {
    registerWorker();
    void refresh();
  }, [refresh]);

  if (!me) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-warm-white p-6 text-center">
        {error ? (
          <>
            <p role="alert" className="text-xl font-bold text-ink">
              {error}
            </p>
            <button type="button" className={PRIMARY} onClick={() => void refresh()}>
              {t("retry")}
            </button>
          </>
        ) : (
          <p className="flex items-center gap-2 text-lg text-ink">
            <LoaderCircle aria-hidden="true" className="size-6 animate-spin motion-reduce:animate-none" />
            {t("loading")}
          </p>
        )}
      </main>
    );
  }
  return (
    <MeCtx.Provider value={{ me, refresh, setMe }}>
      <div className="flex min-h-dvh flex-col bg-warm-white text-ink">
        <header className="sticky top-0 z-10 flex items-center justify-between gap-3 bg-ink px-4 py-3 text-white">
          <span className="text-lg font-black">{t("appName")}</span>
          <span
            data-testid="duty-pill"
            className={cn(
              "rounded-full px-3 py-1 text-base font-bold",
              me.on_duty ? "bg-success-bg text-success" : "bg-white/15 text-white",
            )}
          >
            {me.on_duty ? t("onDuty") : t("offDuty")}
          </span>
        </header>
        <main className="mx-auto flex w-full max-w-lg flex-1 flex-col gap-4 p-4 pb-28">{children}</main>
        <Tabs openOffers={me.open_offers} />
      </div>
    </MeCtx.Provider>
  );
}

function Tabs({ openOffers }: { openOffers: number }) {
  const t = useT();
  const path = usePathname();
  const tabs = [
    { href: "/m", label: t("today"), icon: Home, active: path === "/m" || path.startsWith("/m/jobs") },
    { href: "/m/offers", label: t("offers"), icon: BellRing, active: path.startsWith("/m/offers"), badge: openOffers },
    { href: "/m/profile", label: t("profile"), icon: UserRound, active: path.startsWith("/m/profile") },
  ];
  return (
    <nav aria-label={t("appName")} className="fixed inset-x-0 bottom-0 z-10 border-t-2 border-ink/10 bg-white">
      <ul className="mx-auto grid max-w-lg grid-cols-3">
        {tabs.map(({ href, label, icon: Icon, active, badge }) => (
          <li key={href}>
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex min-h-16 flex-col items-center justify-center gap-0.5 text-base font-bold outline-none focus-visible:bg-warm-white",
                active ? "text-orange-text" : "text-ink",
              )}
            >
              <Icon aria-hidden="true" className="size-7" />
              {label}
              {!!badge && (
                <span className="absolute top-1.5 right-[calc(50%-1.9rem)] min-w-6 rounded-full bg-cta px-1.5 text-sm font-black text-white">
                  {badge}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** A big on / off duty switch (Today and Profile). */
export function DutySwitch() {
  const t = useT();
  const { me, setMe } = useMe();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function flip() {
    setBusy(true);
    setError(null);
    try {
      setMe(await mechanicApi.setOnDuty(!me.on_duty));
    } catch (e) {
      setError(e instanceof MechanicApiError && e.status === 0 ? t("offline") : t("error"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="flex flex-col gap-3 rounded-3xl border-2 border-ink/10 bg-white p-4" aria-labelledby="duty-h">
      <h2 id="duty-h" className="text-2xl font-black">
        {me.on_duty ? t("onDuty") : t("offDuty")}
      </h2>
      <p className="text-lg">{me.on_duty ? t("dutyOnHint") : t("dutyOffHint")}</p>
      <button
        type="button"
        role="switch"
        aria-checked={me.on_duty}
        disabled={busy}
        onClick={flip}
        className={me.on_duty ? SECONDARY : PRIMARY}
      >
        {busy && <LoaderCircle aria-hidden="true" className="size-6 animate-spin motion-reduce:animate-none" />}
        {me.on_duty ? t("goOffDuty") : t("goOnDuty")}
      </button>
      {error && (
        <p role="alert" className="font-bold text-danger">
          {error}
        </p>
      )}
    </section>
  );
}
