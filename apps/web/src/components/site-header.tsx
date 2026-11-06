"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { AccountLink } from "@/components/account/account-link";
import { LanguageSwitch } from "@/components/language-switch";
import { useLocaleHref } from "@/i18n/navigation";

export function SiteHeader() {
  const t = useTranslations("common");
  const href = useLocaleHref();
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-warm-white/90 backdrop-blur">
      <div className="mx-auto flex min-h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-8">
        <Link
          href={href("/")}
          lang="en"
          className="inline-flex min-h-11 items-center rounded-full text-xl font-black tracking-tight text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring"
        >
          Instant&nbsp;<span className="text-orange-text">Mechanic</span>
        </Link>
        <div className="flex items-center gap-2 sm:gap-4">
          <span className="hidden text-sm font-semibold text-ink/70 md:inline">{t("brandTagline")}</span>
          <LanguageSwitch />
          <AccountLink />
        </div>
      </div>
    </header>
  );
}
