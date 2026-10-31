import type { Metadata } from "next";
import { Suspense } from "react";

import { PartCompareView } from "@/components/parts/part-compare";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";

export const metadata: Metadata = {
  title: "Compare parts · Instant Mechanic",
};

export default function Page() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-4xl px-4 py-8 sm:px-8">
          {/* The ids and the car come from the query string: request-time data, so it sits behind Suspense. */}
          <Suspense fallback={<Skeleton className="h-80 rounded-3xl" />}>
            <PartCompareView />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
