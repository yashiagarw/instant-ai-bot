"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";

import { useStatusName, useT } from "@/components/m/i18n";
import { DutySwitch, PRIMARY, useMe } from "@/components/m/shell";
import { mechanicApi, MechanicApiError, type Job } from "@/lib/mechanic-api";

/** Today: on / off duty, new offers, today's jobs. */
export function TodayView() {
  const t = useT();
  const status = useStatusName();
  const { me } = useMe();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    mechanicApi
      .jobs(ctrl.signal)
      .then(setJobs)
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e instanceof MechanicApiError && e.status === 0 ? t("offline") : t("error"));
      });
    return () => ctrl.abort();
  }, [t]);

  return (
    <>
      <h1 className="text-3xl font-black">
        {t("hello")}, {me.first_name}
      </h1>
      <DutySwitch />
      {me.open_offers > 0 && (
        <Link href="/m/offers" className={PRIMARY} data-testid="offers-link">
          {t("openOffers")}: {me.open_offers} · {t("seeOffers")}
        </Link>
      )}
      <section aria-labelledby="jobs-h" className="flex flex-col gap-3">
        <h2 id="jobs-h" className="text-2xl font-black">
          {t("myJobs")}
        </h2>
        {error && (
          <p role="alert" className="text-lg font-bold text-danger">
            {error}
          </p>
        )}
        {jobs === null && !error && <p className="text-lg">{t("loading")}</p>}
        {jobs?.length === 0 && <p className="text-lg">{t("noJobs")}</p>}
        <ul className="flex flex-col gap-3" data-testid="jobs">
          {jobs?.map((j) => (
            <li key={j.id}>
              <Link
                href={`/m/jobs/${j.id}`}
                className="flex min-h-16 items-center justify-between gap-3 rounded-3xl border-2 border-ink/10 bg-white p-4 outline-none focus-visible:ring-4 focus-visible:ring-ring"
              >
                <span className="flex flex-col">
                  <span className="text-lg font-black tabular-nums">{j.reference}</span>
                  <span className="text-base">{j.car}</span>
                  <span className="text-base font-bold text-orange-text">{status(j.status)}</span>
                </span>
                <ChevronRight aria-hidden="true" className="size-7 shrink-0" />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
