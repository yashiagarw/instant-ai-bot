import { CarFront, ClipboardCheck, MessageSquareText } from "lucide-react";

import type { Locale } from "@/i18n/config";
import { serverT } from "@/i18n/server";

const STEPS = [
  { icon: CarFront, key: "step1" },
  { icon: MessageSquareText, key: "step2" },
  { icon: ClipboardCheck, key: "step3" },
] as const;

export function HowItWorks({ locale = "en" }: { locale?: Locale }) {
  const t = serverT(locale, "landing");
  return (
    <section id="how-it-works" aria-labelledby="how-heading" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-12 sm:px-8">
      <h2 id="how-heading" className="text-3xl font-black tracking-tight text-ink sm:text-4xl">
        {t("howTitle")}
      </h2>
      <ol className="mt-6 grid gap-4 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.key} className="flex gap-4 rounded-3xl border border-border bg-white p-5">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-cta text-xl font-black text-white">
              {i + 1}
            </span>
            <div>
              <h3 className="flex items-center gap-2 text-lg font-bold text-ink">
                <s.icon aria-hidden="true" className="size-5 text-orange-text" />
                {t(`${s.key}Title`)}
              </h3>
              <p className="mt-1 text-ink/75">{t(`${s.key}Text`)}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
