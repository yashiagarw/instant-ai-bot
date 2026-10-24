import type { Metadata } from "next";
import { Suspense } from "react";

import { QuestionChat } from "@/components/diagnose/question-chat";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/skeleton";

export const metadata: Metadata = {
  title: "Questions · Instant Mechanic",
};

export default function QuestionsPage() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid">
        <div className="mx-auto max-w-2xl px-4 pb-12 sm:px-8">
          {/* The session id is only known at request time, so the chat sits behind Suspense. */}
          <Suspense fallback={<Skeleton className="mt-8 h-64 rounded-3xl" />}>
            <QuestionChat />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
