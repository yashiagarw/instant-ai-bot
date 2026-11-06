"use client";

import { useEffect } from "react";

import { startErrorReporting } from "@im/ui/observability";

/** Browser errors to Sentry when NEXT_PUBLIC_SENTRY_DSN is set (loaded on demand; nothing otherwise). */
export function ErrorReporting() {
  useEffect(() => {
    startErrorReporting(process.env.NEXT_PUBLIC_SENTRY_DSN, "admin", process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT);
  }, []);
  return null;
}
