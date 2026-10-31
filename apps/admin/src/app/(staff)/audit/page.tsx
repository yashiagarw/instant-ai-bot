import type { Metadata } from "next";

import { AuditView } from "@/components/audit-view";
import { Page } from "@/components/guard";

export const metadata: Metadata = { title: "Audit log" };

export default function AuditPage() {
  return (
    <Page nav="audit" intro="Every staff change and sign-in, newest first. Passwords, codes and phone numbers are masked.">
      <AuditView />
    </Page>
  );
}
