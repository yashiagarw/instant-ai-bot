import Image from "next/image";
import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";

export function Hero() {
  return (
    <section aria-labelledby="hero-heading" className="mx-auto grid max-w-6xl items-center gap-10 px-4 pt-10 pb-14 sm:px-8 md:grid-cols-2 md:pt-16">
      <div className="flex flex-col items-start gap-6">
        <p className="inline-flex items-center gap-2 rounded-full border border-cta/30 bg-white px-4 py-1.5 text-sm font-semibold text-orange-text">
          <ShieldCheck aria-hidden="true" className="size-4" />
          Free AI car diagnosis
        </p>
        <h1
          id="hero-heading"
          className="font-heading text-5xl leading-[0.98] font-black tracking-tight text-ink sm:text-6xl lg:text-7xl"
        >
          Know what&apos;s wrong with your car{" "}
          <span className="bg-linear-to-r from-orange-text to-cta bg-clip-text text-transparent">in 2 minutes</span>
        </h1>
        <p className="max-w-xl text-lg text-ink/80">
          Pick your car, tell us the problem and answer a few quick questions. You get the likely causes, safety
          advice and an estimated repair cost for your car.
        </p>
        <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
          <Button asChild size="cta">
            <Link href="/diagnose">
              Start free diagnosis
              <ArrowRight aria-hidden="true" className="size-5" />
            </Link>
          </Button>
          <Button asChild size="cta" variant="outline" className="border-2 border-ink/15 bg-white text-ink">
            <Link href="#how-it-works">How it works</Link>
          </Button>
        </div>
      </div>
      <Image
        src="/hero-car.svg"
        alt="An orange car with a check mark showing it has been diagnosed"
        width={640}
        height={420}
        priority
        className="h-auto w-full"
      />
    </section>
  );
}
