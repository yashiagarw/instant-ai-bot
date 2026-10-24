"use client";

import { useSearchParams } from "next/navigation";

import { RequestForm } from "@/components/request/request-form";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Reads ?session= (the diagnosis the request is about); the form works without it too. */
export function RequestPage() {
  const session = useSearchParams().get("session");
  return <RequestForm sessionId={session && UUID.test(session) ? session : null} />;
}
