import type { Metadata } from "next";

import { Page } from "@/components/guard";
import { RequestView } from "@/components/requests/request-view";

export const metadata: Metadata = { title: "Request" };

export default async function RequestPage(props: PageProps<"/requests/[id]">) {
  const { id } = await props.params;
  return (
    <Page nav="requests" heading={false}>
      <RequestView id={id} />
    </Page>
  );
}
