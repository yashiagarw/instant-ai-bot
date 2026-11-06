import type { Metadata } from "next";
import Link from "next/link";

import { CONSENTS, GrievanceOfficer, LegalPage, PLACEHOLDER } from "@/components/legal/legal";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Privacy notice · Instant Mechanic" };

export default function Page() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-white">
        <LegalPage title="Privacy notice">
          <p>
            This notice explains how {PLACEHOLDER.company} (&quot;Instant Mechanic&quot;, &quot;we&quot;), {PLACEHOLDER.address}, handles
            your personal data under India&apos;s Digital Personal Data Protection Act, 2023 (DPDP Act). We are the Data
            Fiduciary for the data described here.
          </p>

          <section className="flex flex-col gap-3">
            <h2>What we collect and why</h2>
            <ul className="flex flex-col gap-2">
              <li>
                <strong>Your car and your problem</strong> (make, model, year, fuel, what you choose or type, photos you
                add): to diagnose the likely causes and estimate costs. You can use the diagnosis without giving any
                contact details.
              </li>
              <li>
                <strong>Mobile number</strong> (when you log in): to create your account and send login codes by SMS.
              </li>
              <li>
                <strong>Name, mobile number, area, pincode, address and notes</strong> (when you request a mechanic): to
                contact you and arrange help. The mechanic who accepts the job sees your first name, the address and a
                masked number; calls go through a masking service, so neither of you sees the other&apos;s number.
              </li>
              <li>
                <strong>Notification choices</strong>: SMS, WhatsApp (only with your separate opt-in) and browser alerts.
              </li>
              <li>
                <strong>Technical records</strong>: request ids, error reports with personal data removed, and security
                logs. We do not log phone numbers, names or addresses.
              </li>
            </ul>
          </section>

          <section className="flex flex-col gap-3">
            <h2>Your consent</h2>
            <p>We ask for consent with these exact words, and keep a record of the version and time you agreed:</p>
            <ul className="flex flex-col gap-3" data-testid="consent-texts">
              {CONSENTS.map((c) => (
                <li key={c.version}>
                  <strong>{c.where}</strong> (version <code>{c.version}</code>): &quot;{c.text}&quot;
                </li>
              ))}
            </ul>
            <p>
              You can withdraw consent at any time: turn off WhatsApp or SMS updates in My account, send STOP on WhatsApp,
              or delete your account. Withdrawing does not affect what was done before.
            </p>
          </section>

          <section className="flex flex-col gap-3">
            <h2>Who we share it with</h2>
            <ul className="flex flex-col gap-2">
              <li>The mechanic who accepts your job (as above), and our support team.</li>
              <li>
                Service providers who process data for us under contract: SMS (MSG91), WhatsApp (Meta), email, masked calls
                (Exotel), the &quot;I&apos;m human&quot; check (Cloudflare Turnstile), error reporting (Sentry, with personal
                data removed), hosting and storage. If our AI assistant is switched on, the text you type is sent to it
                with phone numbers, emails and number plates removed first.
              </li>
              <li>Authorities, when the law requires it.</li>
            </ul>
            <p>We do not sell your data or use it for advertising.</p>
          </section>

          <section className="flex flex-col gap-3">
            <h2>How long we keep it</h2>
            <ul className="flex flex-col gap-2">
              <li>Your address, area and notes: removed 90 days after the job is completed or cancelled (the pincode stays).</li>
              <li>What you typed during a diagnosis: removed 90 days after the diagnosis.</li>
              <li>Records of our AI assistant&apos;s use: unlinked from you after 30 days.</li>
              <li>WhatsApp messages you send us (Accept / Reject, STOP / START): deleted 30 days after we handle them.</li>
              <li>Your account: until you delete it. Encrypted backups are kept for 30 days.</li>
              <li>
                The fault a mechanic confirmed for a job is kept without your name or contact details, to improve our
                diagnoses.
              </li>
            </ul>
          </section>

          <section className="flex flex-col gap-3">
            <h2>Your rights</h2>
            <ul className="flex flex-col gap-2">
              <li>
                <strong>Access</strong>: download everything we hold about you from{" "}
                <Link href="/account" className="font-bold text-orange-text underline underline-offset-4">
                  My account
                </Link>{" "}
                (&quot;Download my data&quot;).
              </li>
              <li><strong>Correction</strong>: ask our support team or the Grievance Officer.</li>
              <li>
                <strong>Erasure</strong>: delete your account from My account. Your requests are kept only without your
                name, number, address and notes.
              </li>
              <li><strong>Withdraw consent</strong> at any time (see above).</li>
              <li><strong>Nominate</strong> someone to exercise these rights if you die or cannot act yourself.</li>
              <li>
                <strong>Grievance redressal</strong>: contact the Grievance Officer below. If you are not satisfied, you may
                complain to the Data Protection Board of India.
              </li>
            </ul>
          </section>

          <section className="flex flex-col gap-3">
            <h2>Children</h2>
            <p>Our service is for adults (18 and over). We do not knowingly collect children&apos;s data.</p>
          </section>

          <section className="flex flex-col gap-3">
            <h2>Security</h2>
            <p>
              Data is encrypted in transit (HTTPS) and backups are encrypted. Access is limited to staff who need it, with
              two-factor sign-in, and every access to personal details is logged.
            </p>
          </section>

          <section className="flex flex-col gap-3">
            <h2>Contact and grievances</h2>
            <GrievanceOfficer />
          </section>
        </LegalPage>
      </main>
      <SiteFooter />
    </>
  );
}
