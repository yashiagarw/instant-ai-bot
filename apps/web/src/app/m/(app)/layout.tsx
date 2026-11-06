import { Suspense } from "react";

import { MechanicShell } from "@/components/m/shell";

// Signed-in pages share one shell (who is signed in, the tabs), so moving between tabs does not reload it.
export default function SignedInLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-warm-white" />}>
      <MechanicShell>{children}</MechanicShell>
    </Suspense>
  );
}
