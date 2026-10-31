"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { KeyRound, LogOut, Menu, X } from "lucide-react";

import { cn } from "@im/ui/cn";
import { ChangePassword } from "@/components/change-password";
import { ErrorBox } from "@/components/error-box";
import { adminApi, ApiError, errorMessage, type Me, roleLabel } from "@/lib/api";
import { visibleNav } from "@/lib/nav";

const MeContext = createContext<{ me: Me; reload: () => void } | null>(null);

/** The signed-in staff member (inside StaffShell only). */
export function useMe(): { me: Me; reload: () => void } {
  const ctx = useContext(MeContext);
  if (!ctx) throw new Error("useMe outside StaffShell");
  return ctx;
}

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; me: Me };

/** Every signed-in page: loads who is signed in (or goes to /login), then the sidebar and the page. Staff with a
 * temporary password see only the password form until they choose their own. */
export function StaffShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const reload = useCallback(() => setAttempt((a) => a + 1), []);

  useEffect(() => {
    const ctrl = new AbortController();
    adminApi
      .me(ctrl.signal)
      .then((me) => setState({ kind: "ready", me }))
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        if (e instanceof ApiError && e.status === 401) {
          router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
          return;
        }
        setState({ kind: "error", message: errorMessage(e) });
      });
    return () => ctrl.abort();
  }, [router, attempt]);

  // Close the mobile menu after navigating.
  const [shownFor, setShownFor] = useState(pathname);
  if (shownFor !== pathname) {
    setShownFor(pathname);
    setMenuOpen(false);
  }

  async function signOut() {
    await adminApi.logout().catch(() => undefined);
    router.replace("/login");
  }

  if (state.kind === "loading") {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-ink/70" role="status">
        Loading…
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="mx-auto w-full max-w-lg p-6">
        <ErrorBox message={state.message} onRetry={reload} />
      </div>
    );
  }

  const me = state.me;
  if (me.must_change_password) {
    return (
      <main className="mx-auto flex w-full max-w-lg flex-1 flex-col gap-4 p-4 sm:p-8">
        <h1 className="text-3xl font-black text-ink">Choose your own password</h1>
        <p className="text-ink/80">You signed in with a temporary password. Choose your own before you continue.</p>
        <ChangePassword onDone={reload} />
      </main>
    );
  }

  const items = visibleNav(me.permissions);
  const nav = (
    <nav aria-label="Admin" className="flex flex-col gap-1">
      {items.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.key}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-h-11 items-center gap-3 rounded-full px-4 font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring",
              active && "bg-warm-white text-orange-text",
            )}
          >
            <Icon aria-hidden="true" className="size-5 shrink-0" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
  const account = (
    <div className="flex flex-col gap-2 border-t border-border pt-4">
      <p className="px-4 text-sm text-ink/80">
        <span className="block font-bold text-ink">{me.name}</span>
        {me.roles.map(roleLabel).join(", ")}
      </p>
      <Link
        href="/password"
        className="flex min-h-11 items-center gap-3 rounded-full px-4 font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
      >
        <KeyRound aria-hidden="true" className="size-5" />
        Change password
      </Link>
      <button
        type="button"
        onClick={() => void signOut()}
        className="flex min-h-11 items-center gap-3 rounded-full px-4 text-left font-semibold text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
      >
        <LogOut aria-hidden="true" className="size-5" />
        Sign out
      </button>
    </div>
  );

  return (
    <MeContext.Provider value={{ me, reload }}>
      <div className="flex min-h-dvh flex-col lg:flex-row">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-border bg-white px-4 py-2 lg:hidden">
          <Brand />
          <button
            type="button"
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
            onClick={() => setMenuOpen((o) => !o)}
            className="flex size-11 items-center justify-center rounded-full outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
          >
            {menuOpen ? <X aria-hidden="true" className="size-6" /> : <Menu aria-hidden="true" className="size-6" />}
            <span className="sr-only">Menu</span>
          </button>
        </header>
        {menuOpen && (
          <div id="mobile-menu" className="flex flex-col gap-4 border-b border-border bg-white p-4 lg:hidden">
            {nav}
            {account}
          </div>
        )}
        <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col gap-6 overflow-y-auto border-r border-border bg-white p-4 lg:flex">
          <Brand />
          <div className="flex-1">{nav}</div>
          {account}
        </aside>
        <main className="flex min-w-0 flex-1 flex-col gap-6 p-4 sm:p-8">{children}</main>
      </div>
    </MeContext.Provider>
  );
}

function Brand() {
  return (
    <Link href="/" className="rounded-md px-2 text-lg font-black tracking-tight whitespace-nowrap text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring">
      Instant <span className="text-orange-text">Mechanic</span>
      <span className="ml-2 rounded-full bg-ink px-2 py-0.5 align-middle text-xs font-bold text-white">Admin</span>
    </Link>
  );
}
