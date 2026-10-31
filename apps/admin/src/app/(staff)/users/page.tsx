import type { Metadata } from "next";

import { Page } from "@/components/guard";
import { UsersView } from "@/components/users-view";

export const metadata: Metadata = { title: "Users" };

export default function UsersPage() {
  return (
    <Page nav="users" intro="Staff accounts and customer accounts. Customer phone numbers stay hidden.">
      <UsersView />
    </Page>
  );
}
