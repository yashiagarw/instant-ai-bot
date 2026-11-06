import Image from "next/image";
import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";

import { HeroCar } from "@/components/car3d/hero-car";
import { MotionCta } from "@/components/motion/motion-cta";
import { Button } from "@/components/ui/button";
import { localeHref, type Locale } from "@/i18n/config";
import { serverT } from "@/i18n/server";

export function Hero({ locale = "en" }: { locale?: Locale }) {
  const t = serverT(locale, "landing");
  return (
    <section aria-labelledby="hero-heading" className="mx-auto grid max-w-6xl items-center gap-10 px-4 pt-10 pb-14 sm:px-8 md:grid-cols-2 md:pt-16">
      <div className="flex flex-col items-start gap-6">
        <p className="inline-flex items-center gap-2 rounded-full border border-cta/30 bg-white px-4 py-1.5 text-sm font-semibold text-orange-text">
          <ShieldCheck aria-hidden="true" className="size-4" />
          {t("badge")}
        </p>
        <h1
          id="hero-heading"
          className="font-heading text-5xl leading-[0.98] font-black tracking-tight text-ink sm:text-6xl lg:text-7xl"
        >
          {t("title")}{" "}
          <span className="bg-linear-to-r from-orange-text to-cta bg-clip-text text-transparent">{t("titleAccent")}</span>
        </h1>
        <p className="max-w-xl text-lg text-ink/80">{t("intro")}</p>
        <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
          <MotionCta>
            <Button asChild size="cta">
              <Link href={localeHref(locale, "/diagnose")}>
                {t("start")}
                <ArrowRight aria-hidden="true" className="size-5" />
              </Link>
            </Button>
          </MotionCta>
          <MotionCta>
            <Button asChild size="cta" variant="outline" className="border-2 border-ink/15 bg-white text-ink">
              <Link href="#how-it-works">{t("howLink")}</Link>
            </Button>
          </MotionCta>
        </div>
      </div>
      {/* The picture is the first paint (and the LCP); the 3D car replaces it after the page is interactive, unless
          3D is skipped on this device (components/car3d/hero-car.tsx). */}
      <HeroCar>
        <Image
          src="/hero-car.svg"
          alt={t("heroAlt")}
          width={640}
          height={420}
          preload
          fetchPriority="high"
          className="h-auto w-full"
        />
      </HeroCar>
    </section>
  );
}
