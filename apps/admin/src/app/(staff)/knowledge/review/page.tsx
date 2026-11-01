import type { Metadata } from "next";
import { Suspense } from "react";

import { Page } from "@/components/guard";
import { ReviewView } from "@/components/knowledge/review-view";

export const metadata: Metadata = { title: "Review queues" };

export default function ReviewPage() {
  return (
    <Page nav="knowledge" intro="Questions proposed by the LLM, and questions waiting for a person's sign-off.">
      <Suspense fallback={<p role="status">Loading…</p>}>
        <ReviewView />
      </Suspense>
    </Page>
  );
}
