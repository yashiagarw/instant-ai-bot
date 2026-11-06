"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

export const DISCLAIMER =
  "Results are estimates based on your answers and our data. They are not a replacement for a professional inspection by a mechanic.";

export function SiteFooter() {
  const t = useTranslations("common");
  const link = "inline-flex min-h-11 items-center font-semibold text-ink underline underline-offset-4";
  return (
    <footer className="border-t border-border bg-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-sm text-ink/75 sm:px-8">
        <p className="font-semibold text-ink" lang="en">
          Instant <span className="text-orange-text">Mechanic</span> · Delhi NCR
        </p>
        <p>{t("disclaimer")}</p>
        {/* Safety advice: English until a reviewed Hindi version exists. */}
        <p lang="en">In an emergency or if you feel unsafe, move away from the car and call 112.</p>
        <nav aria-label={t("legal")} className="flex flex-wrap gap-x-5">
          <Link href="/privacy" className={link}>
            {t("privacy")}
          </Link>
          <Link href="/terms" className={link}>
            {t("terms")}
          </Link>
          <Link href="/disclaimer" className={link}>
            {t("disclaimerLink")}
          </Link>
        </nav>
      </div>
    </footer>
  );
}
