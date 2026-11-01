import type { Metadata } from "next";
import { Suspense } from "react";

import { Page } from "@/components/guard";
import { MechanicEditor } from "@/components/mechanics/mechanic-editor";

export const metadata: Metadata = { title: "Mechanic" };

export default async function MechanicPage(props: PageProps<"/mechanics/[id]">) {
  const { id } = await props.params;
  return (
    <Page nav="mechanics" heading={false}>
      <Suspense fallback={<p role="status">Loading…</p>}>
        <MechanicEditor id={Number(id)} />
      </Suspense>
    </Page>
  );
}
