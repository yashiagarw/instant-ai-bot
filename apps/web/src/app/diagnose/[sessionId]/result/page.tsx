import type { Metadata } from "next";
import { Suspense } from "react";

import { ResultView } from "@/components/result/result-view";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";

export const metadata: Metadata = {
  title: "Your result · Instant Mechanic",
};

export default function ResultPage() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
          {/* Opened from a shared link too: the session id is request-time data, so it sits behind Suspense. */}
          <Suspense fallback={<Skeleton className="h-80 rounded-3xl" />}>
            <ResultView />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
