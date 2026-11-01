import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Page } from "@/components/guard";
import { KnowledgeView } from "@/components/knowledge/knowledge-view";

export const metadata: Metadata = { title: "Knowledge" };

export default function KnowledgePage() {
  return (
    <Page
      nav="knowledge"
      intro={
        <>
          Edit faults, questions, tiles, categories and safety rules in a draft, then publish it on the Datasets page. Review queues:{" "}
          <Link href="/knowledge/review" className="font-bold text-orange-text underline underline-offset-4">
            proposed questions and sign-off
          </Link>
          .
        </>
      }
    >
      <Suspense fallback={<p role="status">Loading…</p>}>
        <KnowledgeView />
      </Suspense>
    </Page>
  );
}
