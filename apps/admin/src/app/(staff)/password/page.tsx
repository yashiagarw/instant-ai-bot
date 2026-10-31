import type { Metadata } from "next";

import { PasswordPage } from "@/components/password-page";

export const metadata: Metadata = { title: "Change password" };

export default function Password() {
  return <PasswordPage />;
}
