import type { Metadata } from "next";

import { Page } from "@/components/guard";
import { UnlistedView } from "@/components/vehicles/unlisted-view";

export const metadata: Metadata = { title: "Vehicles" };

export default function VehiclesPage() {
  return (
    <Page nav="vehicles" intro="The car catalogue. For now: the review queue of cars customers typed because they were not listed.">
      <UnlistedView />
    </Page>
  );
}
