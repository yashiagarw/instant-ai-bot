import Link from "next/link";
import type { ReactNode } from "react";

// Privacy notice, terms and disclaimer (Phase 5.4). DRAFTS pending legal review: the company's legal name, address
// and the grievance officer are placeholders in [BRACKETS]. The consent texts below are the exact wording the app
// shows and stores (backend: accounts CONSENT_TEXT, requests CONSENT_TEXT, notify/optins.py); a backend test
// (backend/tests/test_legal_and_backups.py) fails if they drift apart. Retention periods match the RETENTION_* settings.

export const PLACEHOLDER = {
  company: "[COMPANY LEGAL NAME]",
  address: "[REGISTERED OFFICE ADDRESS]",
  grievanceName: "[GRIEVANCE OFFICER NAME]",
  grievanceEmail: "[grievance@instantmechanic.online]",
  grievancePhone: "[GRIEVANCE OFFICER PHONE]",
  city: "[CITY FOR COURTS]",
};

export const CONSENTS = [
  {
    where: "Logging in (account)",
    version: "account-v1",
    text: "I agree that Instant Mechanic stores my mobile number to create my account and keep my cars, diagnoses and requests in it. I can delete my account and this data at any time.",
  },
  {
    where: "Requesting a mechanic",
    version: "request-v1",
    text: "I agree that Instant Mechanic's team may use my name, mobile number, location and the car and diagnosis details above to contact me and arrange help for this request.",
  },
  {
    where: "WhatsApp updates (customers, optional)",
    version: "whatsapp-customer-v1",
    text: "Send me updates about my mechanic request on WhatsApp from Instant Mechanic (mechanic assigned, on the way, arrived, job done). I can stop them at any time by sending STOP.",
  },
  {
    where: "WhatsApp job offers (mechanics)",
    version: "whatsapp-mechanic-v1",
    text: "I agree to get job offers from Instant Mechanic on WhatsApp, with Accept and Reject buttons. I can stop them at any time by sending STOP.",
  },
] as const;

export const UPDATED = "6 November 2026";

export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8 text-ink sm:px-8 [&_h2]:text-2xl [&_h2]:font-black [&_li]:ml-5 [&_li]:list-disc [&_p]:leading-relaxed">
      <p role="note" className="rounded-2xl border-2 border-amber-text bg-amber-bg p-4 font-bold text-amber-text" data-testid="draft-banner">
        Draft, pending legal review. Not yet in force. Text in [BRACKETS] is still to be filled in.
      </p>
      <div>
        <h1 className="text-4xl font-black tracking-tight sm:text-5xl">{title}</h1>
        <p className="mt-2 text-ink/70">Last updated {UPDATED}</p>
      </div>
      {children}
      <nav aria-label="Legal" className="flex flex-wrap gap-x-5 border-t border-border pt-4">
        <Link href="/privacy" className="inline-flex min-h-11 items-center font-bold text-orange-text underline underline-offset-4">
          Privacy notice
        </Link>
        <Link href="/terms" className="inline-flex min-h-11 items-center font-bold text-orange-text underline underline-offset-4">
          Terms of use
        </Link>
        <Link href="/disclaimer" className="inline-flex min-h-11 items-center font-bold text-orange-text underline underline-offset-4">
          Disclaimer
        </Link>
      </nav>
    </article>
  );
}

export function GrievanceOfficer() {
  return (
    <address className="not-italic rounded-2xl bg-warm-white p-4" data-testid="grievance-officer">
      <strong>Grievance Officer:</strong> {PLACEHOLDER.grievanceName}
      <br />
      {PLACEHOLDER.company}, {PLACEHOLDER.address}
      <br />
      Email: {PLACEHOLDER.grievanceEmail} · Phone: {PLACEHOLDER.grievancePhone}
      <br />
      We acknowledge a grievance within 48 hours and resolve it within 30 days.
    </address>
  );
}
