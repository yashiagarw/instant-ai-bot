import type { Metadata } from "next";

import { VersionView } from "@/components/datasets/version-view";
import { Page } from "@/components/guard";

export const metadata: Metadata = { title: "Dataset version" };

export default async function DatasetVersionPage(props: PageProps<"/datasets/[id]">) {
  const { id } = await props.params;
  return (
    <Page nav="datasets" heading={false}>
      <VersionView id={Number(id)} />
    </Page>
  );
}
