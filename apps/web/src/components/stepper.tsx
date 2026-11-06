"use client";

import { Check } from "lucide-react";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

export const STEPS = ["Car", "Problem", "Questions", "Result"] as const;
export type Step = (typeof STEPS)[number];

export function Stepper({ current }: { current: Step }) {
  const t = useTranslations("common.steps");
  const index = STEPS.indexOf(current);
  return (
    <nav aria-label={t("label")}>
      <ol className="grid grid-cols-4 gap-2">
        {STEPS.map((step, i) => {
          const done = i < index;
          const active = i === index;
          return (
            <li key={step} aria-current={active ? "step" : undefined} className="flex flex-col items-center gap-1.5">
              <span
                aria-hidden="true"
                className={cn(
                  "flex size-9 items-center justify-center rounded-full border-2 text-sm font-bold",
                  done && "border-cta bg-cta text-white",
                  active && "border-cta bg-white text-orange-text",
                  !done && !active && "border-ink/20 bg-white text-ink/70",
                )}
              >
                {done ? <Check className="size-4" /> : i + 1}
              </span>
              <span className={cn("text-xs font-semibold sm:text-sm", active ? "text-ink" : "text-ink/70")}>
                {t(step)}
                {done && <span className="sr-only"> {t("done")}</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
