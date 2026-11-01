import type { Metadata } from "next";

import { Page } from "@/components/guard";
import { VehiclesView } from "@/components/vehicles/vehicles-view";

export const metadata: Metadata = { title: "Vehicles" };

export default function VehiclesPage() {
  return (
    <Page nav="vehicles" intro="The car catalogue (makes, models, generations, variants) and the cars customers typed because they were not listed.">
      <VehiclesView />
    </Page>
  );
}
