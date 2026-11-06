import type { Metadata } from "next";
import { Suspense } from "react";

import { DiagnoseFlow } from "@/components/diagnose/diagnose-flow";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";
import { Localized } from "@/i18n/localized";
import { localeOf, pageMetadata, serverT } from "@/i18n/server";
import { Stepper } from "@/components/stepper";

export async function generateMetadata({ params }: PageProps<"/[locale]/diagnose">): Promise<Metadata> {
  const locale = await localeOf(params);
  const t = serverT(locale, "diagnose");
  return pageMetadata(locale, "/diagnose", t("metaTitleCar"));
}

function FlowSkeleton() {
  return (
    <div className="flex flex-col gap-8">
      <Stepper current="Car" />
      <Skeleton className="h-12 w-3/4" />
      <Skeleton className="h-14 rounded-full" />
    </div>
  );
}

export default function DiagnosePage({ params }: PageProps<"/[locale]/diagnose">) {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8 sm:py-12">
          {/* useSearchParams (the topic picked on the home page) and the language in the URL need a Suspense boundary. */}
          <Suspense fallback={<FlowSkeleton />}>
            <Localized params={params} namespaces={["diagnose"]}>
              <DiagnoseFlow />
            </Localized>
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
