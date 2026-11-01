import type { Metadata } from "next";

import { Page } from "@/components/guard";
import { ReplayView } from "@/components/quality/replay-view";

export const metadata: Metadata = { title: "Session replay" };

export default async function ReplayPage(props: PageProps<"/quality/sessions/[id]">) {
  const { id } = await props.params;
  return (
    <Page nav="quality" heading={false}>
      <ReplayView id={id} />
    </Page>
  );
}
