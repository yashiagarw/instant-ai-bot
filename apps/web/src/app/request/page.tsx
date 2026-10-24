import type { Metadata } from "next";
import { Suspense } from "react";

import { RequestPage } from "@/components/request/request-page";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";

export const metadata: Metadata = {
  title: "Request a Mechanic · Instant Mechanic",
};

export default function Page() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-2xl px-4 py-8 sm:px-8 sm:py-12">
          {/* ?session= is request-time data, so the form sits behind Suspense. */}
          <Suspense fallback={<Skeleton className="h-96 rounded-3xl" />}>
            <RequestPage />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
