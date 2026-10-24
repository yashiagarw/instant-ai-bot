import { HowItWorks } from "@/components/landing/how-it-works";
import { Hero } from "@/components/landing/hero";
import { ProblemTiles } from "@/components/landing/problem-tiles";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid pb-12">
        <Hero />
        <HowItWorks />
        <ProblemTiles />
      </main>
      <SiteFooter />
    </>
  );
}
