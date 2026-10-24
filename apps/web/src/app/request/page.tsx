import type { Metadata } from "next";
import Link from "next/link";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "Request a Mechanic · Instant Mechanic",
};

// Placeholder until the request form is built (next task). Collecting contact details needs the consent flow.
export default function RequestPage() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-12 sm:px-8">
          <h1 className="text-4xl font-black tracking-tight text-ink">Request a Mechanic</h1>
          <p className="text-lg text-ink/80">
            The request form is coming soon. If you are in danger, move away from the car and call 112.
          </p>
          <Link href="/" className="inline-flex min-h-11 items-center font-bold text-orange-text underline underline-offset-4">
            Back to home
          </Link>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
