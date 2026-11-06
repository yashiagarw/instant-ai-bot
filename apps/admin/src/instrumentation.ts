// Server-side errors of the Next.js server (Phase 5.4): one JSON line each (masked: no phone numbers, emails or
// tokens), and to Sentry when SENTRY_DSN is set (off otherwise). Browser errors: src/components/error-reporting.tsx.
import type { Instrumentation } from "next";

import { scrubText, sendServerError } from "@im/ui/observability";

export const onRequestError: Instrumentation.onRequestError = async (error, request) => {
  const err = error as Error & { digest?: string };
  const requestId = (request.headers["x-request-id"] as string | undefined) ?? err.digest ?? "-";
  console.error(
    JSON.stringify({
      time: new Date().toISOString(),
      level: "ERROR",
      service: "admin",
      message: scrubText(err.message ?? String(error)),
      path: request.path.split("?")[0],
      request_id: requestId,
    }),
  );
  await sendServerError(process.env.SENTRY_DSN, error, { app: "admin", request_id: requestId }, process.env.SENTRY_ENVIRONMENT);
};
