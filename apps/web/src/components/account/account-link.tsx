"use client";

import Link from "next/link";
import { CircleUser } from "lucide-react";

import { accountApi } from "@/lib/api";
import { useLoad } from "@/lib/use-load";

/** "Log in" for visitors, "My account" once logged in (the cookie is HttpOnly: only the API can tell). */
export function AccountLink() {
  const me = useLoad("me", (signal) => accountApi.me(signal));
  const loggedIn = me.state.status === "ready";
  return (
    <Link
      href={loggedIn ? "/account" : "/login"}
      className="inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 font-bold text-ink outline-none hover:text-orange-text focus-visible:ring-3 focus-visible:ring-ring"
      data-testid="account-link"
    >
      <CircleUser aria-hidden="true" className="size-5 text-orange-text" />
      {loggedIn ? "My account" : "Log in"}
    </Link>
  );
}
