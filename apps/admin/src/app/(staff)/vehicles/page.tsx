import type { Metadata } from "next";

import { Page } from "@/components/guard";

export const metadata: Metadata = { title: "Vehicles" };

export default function Placeholder() {
  return <Page nav="vehicles" />;
}
