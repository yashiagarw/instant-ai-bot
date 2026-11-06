import type { Metadata } from "next";
import { Suspense } from "react";

import { QuestionChat } from "@/components/diagnose/question-chat";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";
import { Localized } from "@/i18n/localized";
import { localeOf, serverT } from "@/i18n/server";

export async function generateMetadata({ params }: PageProps<"/[locale]/diagnose/[sessionId]">): Promise<Metadata> {
  const locale = await localeOf(params);
  const t = serverT(locale, "diagnose");
  return { title: t("metaTitleQuestions") };
}

export default function QuestionsPage({ params }: PageProps<"/[locale]/diagnose/[sessionId]">) {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-2xl px-4 pb-12 sm:px-8">
          {/* The session id is only known at request time, so the chat sits behind Suspense. */}
          <Suspense fallback={<Skeleton className="mt-8 h-64 rounded-3xl" />}>
            <Localized params={params} namespaces={["diagnose"]}>
              <QuestionChat />
            </Localized>
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
