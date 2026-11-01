"use client";

import type { ReactNode } from "react";
import { Construction, Lock } from "lucide-react";

import { useMe } from "@/components/staff-shell";
import { can, navItem } from "@/lib/nav";

/** A page's heading and content, or "no access" when the menu item would be hidden for this staff member (opened
 * by its address). The API refuses those calls anyway. */
export function Page({
  nav,
  children,
  intro,
  heading = true,
}: {
  nav: string;
  children?: ReactNode;
  intro?: ReactNode;
  /** false: the page shows its own heading (a detail page). */
  heading?: boolean;
}) {
  const { me } = useMe();
  const item = navItem(nav);
  if (!can(me.permissions, item.anyOf)) {
    return (
      <section className="flex flex-col items-start gap-3 rounded-3xl border border-border bg-white p-6" data-testid="no-access">
        <Lock aria-hidden="true" className="size-6 text-orange-text" />
        <h1 className="text-2xl font-black text-ink">No access</h1>
        <p className="text-ink/80">Your role doesn&apos;t include {item.label}. Ask a super admin if you need it.</p>
      </section>
    );
  }
  return (
    <>
      {heading && (
        <header className="flex flex-col gap-1">
          <h1 className="text-3xl font-black tracking-tight text-ink sm:text-4xl">{item.label}</h1>
          {intro && <div className="text-ink/80">{intro}</div>}
        </header>
      )}
      {item.placeholder ? (
        <section className="flex flex-col items-start gap-2 rounded-3xl border border-dashed border-border bg-white p-6" data-testid="placeholder">
          <Construction aria-hidden="true" className="size-6 text-orange-text" />
          <h2 className="text-lg font-bold text-ink">Coming soon</h2>
          <p className="text-ink/80">{item.placeholder}</p>
        </section>
      ) : (
        children
      )}
    </>
  );
}
