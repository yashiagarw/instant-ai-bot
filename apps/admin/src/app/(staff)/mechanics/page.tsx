import type { Metadata } from "next";

import { Page } from "@/components/guard";
import { MechanicsView } from "@/components/mechanics/mechanics-view";

export const metadata: Metadata = { title: "Mechanics" };

export default function MechanicsPage() {
  return (
    <Page nav="mechanics" intro="Mechanics, their skills, zones and weekly shifts, and who is on duty. Changes are live and audited.">
      <MechanicsView />
    </Page>
  );
}
