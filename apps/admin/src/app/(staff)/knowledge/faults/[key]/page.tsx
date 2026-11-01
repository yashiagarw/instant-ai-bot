import type { Metadata } from "next";
import { Suspense } from "react";

import { Page } from "@/components/guard";
import { FaultEditorPage } from "@/components/knowledge/fault-editor";

export const metadata: Metadata = { title: "Fault" };

export default async function FaultPage(props: PageProps<"/knowledge/faults/[key]">) {
  const { key } = await props.params;
  return (
    <Page nav="knowledge" heading={false}>
      <Suspense fallback={<p role="status">Loading…</p>}>
        <FaultEditorPage faultKey={decodeURIComponent(key)} />
      </Suspense>
    </Page>
  );
}
