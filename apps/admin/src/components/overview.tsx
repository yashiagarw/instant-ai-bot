"use client";

import Link from "next/link";

import { Page } from "@/components/guard";
import { useMe } from "@/components/staff-shell";
import { roleLabel } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { visibleNav } from "@/lib/nav";

export function Overview() {
  const { me } = useMe();
  const items = visibleNav(me.permissions).filter((i) => i.key !== "overview");
  return (
    <Page nav="overview" intro={<>Welcome, {me.name}. You are signed in as {me.roles.map(roleLabel).join(", ")}.</>}>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.key}>
              <Link
                href={item.href}
                className="flex min-h-24 items-start gap-3 rounded-3xl border border-border bg-white p-5 outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring"
              >
                <Icon aria-hidden="true" className="size-6 shrink-0 text-orange-text" />
                <span>
                  <span className="block text-lg font-black text-ink">{item.label}</span>
                  <span className="text-sm text-ink/75">{item.placeholder ?? "Open"}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="text-sm text-ink/70">Your session ends at {dateTime(me.session_expires_at)}, or after 30 minutes without activity.</p>
    </Page>
  );
}
