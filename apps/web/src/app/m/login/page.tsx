import { Suspense } from "react";

import { MechanicLoginView } from "@/components/m/login-view";

export default function Page() {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-ink" />}>
      <MechanicLoginView />
    </Suspense>
  );
}
