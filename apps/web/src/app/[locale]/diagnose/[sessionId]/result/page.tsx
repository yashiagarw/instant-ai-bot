import type { Metadata } from "next";
import { Suspense } from "react";

import { ResultView } from "@/components/result/result-view";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";
import { Localized } from "@/i18n/localized";
import { localeOf, serverT } from "@/i18n/server";

export async function generateMetadata({ params }: PageProps<"/[locale]/diagnose/[sessionId]/result">): Promise<Metadata> {
  const locale = await localeOf(params);
  const t = serverT(locale, "result");
  return { title: t("metaTitle") };
}

export default function ResultPage({ params }: PageProps<"/[locale]/diagnose/[sessionId]/result">) {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
          {/* Opened from a shared link too: the session id is request-time data, so it sits behind Suspense. */}
          <Suspense fallback={<Skeleton className="h-80 rounded-3xl" />}>
            <Localized params={params} namespaces={["result", "carParts"]}>
              <ResultView />
            </Localized>
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
