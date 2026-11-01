import type { Metadata } from "next";
import { Suspense } from "react";

import { Page } from "@/components/guard";
import { PartsView } from "@/components/parts/parts-view";

export const metadata: Metadata = { title: "Parts & Prices" };

export default function PartsPage() {
  return (
    <Page nav="parts" intro="Parts, pictures, fits, prices and labour rates, edited in a draft and published on the Datasets page.">
      <Suspense fallback={<p role="status">Loading…</p>}>
        <PartsView />
      </Suspense>
    </Page>
  );
}
