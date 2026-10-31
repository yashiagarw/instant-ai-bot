import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountView } from "@/components/account/account-view";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";

export const metadata: Metadata = {
  title: "My account · Instant Mechanic",
  robots: { index: false },
};

export default function Page() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-2xl px-4 py-8 sm:px-8">
          {/* Reads the login cookie and the query string at request time, so it sits behind Suspense. */}
          <Suspense fallback={<Skeleton className="h-80 rounded-3xl" />}>
            <AccountView />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
