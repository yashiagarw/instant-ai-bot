import type { Metadata } from "next";

import { Page } from "@/components/guard";

export const metadata: Metadata = { title: "Requests" };

export default function Placeholder() {
  return <Page nav="requests" />;
}
