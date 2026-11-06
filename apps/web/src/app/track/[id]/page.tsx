import type { Metadata } from "next";
import { Suspense } from "react";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";
import { TrackingView } from "@/components/track/tracking-view";

export const metadata: Metadata = {
  title: "Track your request · Instant Mechanic",
  robots: { index: false },
};

export default function Page() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-2xl px-4 py-8 sm:px-8">
          <Suspense fallback={<Skeleton className="h-96 rounded-3xl" />}>
            <TrackingView />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
