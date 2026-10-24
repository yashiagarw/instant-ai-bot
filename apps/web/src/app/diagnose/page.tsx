import type { Metadata } from "next";
import { Suspense } from "react";

import { DiagnoseFlow } from "@/components/diagnose/diagnose-flow";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";
import { Stepper } from "@/components/stepper";

export const metadata: Metadata = {
  title: "Pick your car · Instant Mechanic",
};

function FlowSkeleton() {
  return (
    <div className="flex flex-col gap-8">
      <Stepper current="Car" />
      <Skeleton className="h-12 w-3/4" />
      <Skeleton className="h-14 rounded-full" />
    </div>
  );
}

export default function DiagnosePage() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8 sm:py-12">
          {/* useSearchParams (the topic picked on the home page) needs a Suspense boundary. */}
          <Suspense fallback={<FlowSkeleton />}>
            <DiagnoseFlow />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
