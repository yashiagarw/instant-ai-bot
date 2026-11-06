import type { Metadata } from "next";

import { AutoOfferView } from "@/components/dispatch/auto-offer-view";
import { Page } from "@/components/guard";

export const metadata: Metadata = { title: "Auto-offer" };

export default function DispatchPage() {
  return (
    <Page
      nav="dispatch"
      intro="Where auto-offer is on, new requests are offered to the best suggested mechanic without waiting for an agent, and to the next one when an offer expires. Off by default. Safety-critical requests are always left to support, and taking a request stops auto-offer for it."
    >
      <AutoOfferView />
    </Page>
  );
}
