import type { Metadata } from "next";

import { DatasetsView } from "@/components/datasets/datasets-view";
import { Page } from "@/components/guard";

export const metadata: Metadata = { title: "Datasets" };

export default function DatasetsPage() {
  return (
    <Page
      nav="datasets"
      intro="Upload a category file, check what it changes and how the evaluation compares, then publish it or roll a category back."
    >
      <DatasetsView />
    </Page>
  );
}
