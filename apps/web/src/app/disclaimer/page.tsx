import type { Metadata } from "next";

import { LegalPage } from "@/components/legal/legal";
import { DISCLAIMER, SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Disclaimer · Instant Mechanic" };

export default function Page() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-white">
        <LegalPage title="Disclaimer">
          <p className="text-xl font-bold">{DISCLAIMER}</p>
          <section className="flex flex-col gap-3">
            <h2>Diagnosis</h2>
            <p>
              Likely causes are worked out from your answers and our data about common faults. They are not certain, and a
              mechanic must inspect the car to confirm the fault. Each result says how well it fits your car: part fit
              verified, an estimate for your car&apos;s price segment, or general guidance.
            </p>
          </section>
          <section className="flex flex-col gap-3">
            <h2>Costs</h2>
            <p>
              Costs are approximate ranges for your car&apos;s price segment, shown with the date the prices were last
              checked. The real price depends on the inspection, the parts and the work needed.
            </p>
          </section>
          <section className="flex flex-col gap-3">
            <h2>Safety</h2>
            <p>
              Safety warnings are shown whenever your answers match a known risk. If you see one, stop driving. In an
              emergency, or if you feel unsafe, move away from the car and call 112. Do not try repairs you are not trained
              for.
            </p>
          </section>
        </LegalPage>
      </main>
      <SiteFooter />
    </>
  );
}
