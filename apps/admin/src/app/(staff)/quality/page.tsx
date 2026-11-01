import type { Metadata } from "next";
import { Suspense } from "react";

import { Page } from "@/components/guard";
import { QualityView } from "@/components/quality/quality-view";

export const metadata: Metadata = { title: "Quality" };

export default function QualityPage() {
  return (
    <Page nav="quality" intro="How well the diagnosis works: evaluation, mechanics' confirmed faults, customer feedback and sessions to review.">
      <Suspense fallback={<p role="status">Loading…</p>}>
        <QualityView />
      </Suspense>
    </Page>
  );
}
