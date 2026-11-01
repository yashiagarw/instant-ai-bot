import type { Metadata } from "next";
import { Suspense } from "react";

import { Page } from "@/components/guard";
import { RequestsQueue } from "@/components/requests/queue-view";

export const metadata: Metadata = { title: "Requests" };

export default function RequestsPage() {
  return (
    <Page nav="requests" intro="Mechanic requests: safety-critical first, then urgent, then the oldest.">
      <Suspense fallback={<p role="status">Loading…</p>}>
        <RequestsQueue />
      </Suspense>
    </Page>
  );
}
