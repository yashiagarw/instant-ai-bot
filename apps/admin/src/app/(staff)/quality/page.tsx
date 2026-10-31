import type { Metadata } from "next";

import { Page } from "@/components/guard";

export const metadata: Metadata = { title: "Quality" };

export default function Placeholder() {
  return <Page nav="quality" />;
}
