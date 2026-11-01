import type { Metadata } from "next";
import { Suspense } from "react";

import { Page } from "@/components/guard";
import { PartEditorPage } from "@/components/parts/part-editor";

export const metadata: Metadata = { title: "Part" };

export default async function PartPage(props: PageProps<"/parts/[...key]">) {
  const { key } = await props.params;
  return (
    <Page nav="parts" heading={false}>
      <Suspense fallback={<p role="status">Loading…</p>}>
        <PartEditorPage partKey={key.map(decodeURIComponent).join("/")} />
      </Suspense>
    </Page>
  );
}
