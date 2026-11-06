import type { Metadata } from "next";
import Link from "next/link";

import { GrievanceOfficer, LegalPage, PLACEHOLDER } from "@/components/legal/legal";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Terms of use · Instant Mechanic" };

export default function Page() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-white">
        <LegalPage title="Terms of use">
          <p>
            These terms apply to instantmechanic.online and its apps, run by {PLACEHOLDER.company}, {PLACEHOLDER.address}.
            By using the service you agree to them.
          </p>
          <section className="flex flex-col gap-3">
            <h2>What we offer</h2>
            <p>
              An online car diagnosis that suggests likely causes, safety advice and estimated costs, and a way to request a
              mechanic in Delhi NCR. Results are estimates: read the{" "}
              <Link href="/disclaimer" className="font-bold text-orange-text underline underline-offset-4">
                disclaimer
              </Link>
              .
            </p>
          </section>
          <section className="flex flex-col gap-3">
            <h2>Requesting a mechanic</h2>
            <ul className="flex flex-col gap-2">
              <li>Our team confirms the job, the price and the time with you before work starts.</li>
              <li>The final price depends on what the mechanic finds on inspection and the parts needed.</li>
              <li>[PAYMENT, CANCELLATION AND WARRANTY TERMS, TO BE ADDED]</li>
              <li>[RELATIONSHIP BETWEEN INSTANT MECHANIC AND THE MECHANICS, TO BE ADDED]</li>
            </ul>
          </section>
          <section className="flex flex-col gap-3">
            <h2>Your part</h2>
            <ul className="flex flex-col gap-2">
              <li>Give true details, and only your own contact details or ones you are allowed to share.</li>
              <li>Do not misuse the service: no automated access, no attempts to get around its limits or security.</li>
              <li>In an emergency, or if you feel unsafe, move away from the car and call 112.</li>
            </ul>
          </section>
          <section className="flex flex-col gap-3">
            <h2>Liability</h2>
            <p>[LIMITATION OF LIABILITY, TO BE WRITTEN WITH LEGAL REVIEW]</p>
          </section>
          <section className="flex flex-col gap-3">
            <h2>Law and disputes</h2>
            <p>These terms are governed by the laws of India. Courts at {PLACEHOLDER.city} have jurisdiction.</p>
          </section>
          <section className="flex flex-col gap-3">
            <h2>Contact</h2>
            <GrievanceOfficer />
          </section>
        </LegalPage>
      </main>
      <SiteFooter />
    </>
  );
}
