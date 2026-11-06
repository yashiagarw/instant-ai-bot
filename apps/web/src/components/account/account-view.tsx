"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { Car, ClipboardList, History } from "lucide-react";

import { NotificationChoices } from "@/components/account/notification-choices";
import { ErrorMessage } from "@/components/error-message";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { accountApi, API_URL, ApiError, errorMessage, type Me, type RequestSummary, type SavedCar, type SessionSummary } from "@/lib/api";
import { shortDate } from "@/lib/format";

type Data = { me: Me; cars: SavedCar[]; sessions: SessionSummary[]; requests: RequestSummary[] };

const SESSION_STATUS: Record<SessionSummary["status"], string> = {
  completed: "Finished",
  in_progress: "Not finished",
  abandoned: "Stopped",
};

function Section({ id, title, icon, children }: { id: string; title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-5">
      <h2 id={id} className="flex items-center gap-2 text-2xl font-black text-ink">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function DeleteAccount({ onDeleted }: { onDeleted: () => void }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <section aria-labelledby={`${id}-h`} className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-5">
      <h2 id={`${id}-h`} className="text-xl font-black text-ink">
        Delete my account
      </h2>
      <p className="text-ink/85">
        This removes your mobile number, saved cars, diagnosis history and anything you uploaded. Your mechanic requests
        are kept only without your name, number, address and notes (the fault the mechanic found helps us improve). It
        cannot be undone.
      </p>
      {!open ? (
        <Button variant="outline" className="h-12 self-start rounded-full px-6 text-base font-bold" onClick={() => setOpen(true)}>
          Delete my account
        </Button>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              await accountApi.deleteAccount();
              onDeleted();
            } catch (err) {
              setError(errorMessage(err));
              setBusy(false);
            }
          }}
        >
          <label htmlFor={`${id}-confirm`} className="font-bold text-ink">
            Type DELETE to confirm
          </label>
          <input
            id={`${id}-confirm`}
            value={typed}
            autoComplete="off"
            onChange={(e) => setTyped(e.target.value)}
            className="h-12 w-48 rounded-full border-2 border-ink/15 bg-white px-4 text-base text-ink outline-none focus-visible:border-cta focus-visible:ring-3 focus-visible:ring-ring/40"
          />
          {error && (
            <p role="alert" className="font-semibold text-orange-text">
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <Button type="submit" disabled={typed !== "DELETE" || busy} className="h-12 rounded-full bg-ink px-6 text-base font-bold text-white hover:bg-ink/85">
              {busy ? "Deleting…" : "Delete everything"}
            </Button>
            <Button type="button" variant="outline" className="h-12 rounded-full px-6 text-base font-bold" onClick={() => setOpen(false)}>
              Keep my account
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}

/** /account: My garage, Diagnosis history, My requests, log out and account deletion. Logged-out visitors go to /login. */
export function AccountView() {
  const router = useRouter();
  const [state, setState] = useState<{ status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: Data }>({
    status: "loading",
  });
  const [attempt, setAttempt] = useState(0);
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    Promise.all([
      accountApi.me(ctrl.signal),
      accountApi.cars(ctrl.signal),
      accountApi.sessions(ctrl.signal),
      accountApi.requests(ctrl.signal),
    ])
      .then(([me, cars, sessions, requests]) => setState({ status: "ready", data: { me, cars, sessions, requests } }))
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        if (e instanceof ApiError && e.status === 401) router.replace("/login?next=/account");
        else setState({ status: "error", message: errorMessage(e) });
      });
    return () => ctrl.abort();
  }, [attempt, router]);

  if (deleted) {
    return (
      <section role="status" className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-5">
        <h1 className="text-3xl font-black text-ink">Your account is deleted</h1>
        <p className="text-ink/85">Your mobile number, cars, history and requests have been removed.</p>
        <Link href="/" className="font-bold text-orange-text underline underline-offset-4">
          Back to the home page
        </Link>
      </section>
    );
  }
  if (state.status === "loading") {
    return (
      <div className="flex flex-col gap-4" aria-busy="true">
        <span role="status" className="sr-only">
          Loading your account…
        </span>
        <Skeleton className="h-28 rounded-3xl" />
        <Skeleton className="h-48 rounded-3xl" />
      </div>
    );
  }
  if (state.status === "error") return <ErrorMessage message={state.message} onRetry={() => setAttempt((a) => a + 1)} />;
  const { me, cars, sessions, requests } = state.data;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl leading-tight font-black tracking-tight text-ink">My account</h1>
          <p className="mt-1 text-ink/80 tabular-nums">{me.user.phone_masked}</p>
        </div>
        <Button
          variant="outline"
          className="h-12 self-start rounded-full px-6 text-base font-bold sm:self-auto"
          onClick={async () => {
            await accountApi.logout().catch(() => undefined);
            router.push("/");
          }}
        >
          Log out
        </Button>
      </header>

      <Section id="garage" title="My garage" icon={<Car aria-hidden="true" className="size-6 text-orange-text" />}>
        {cars.length === 0 ? (
          <p className="text-ink/80">Cars you diagnose while logged in are saved here.</p>
        ) : (
          <ul className="flex flex-col gap-2" data-testid="garage">
            {cars.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 rounded-2xl bg-warm-white p-3">
                <span className="font-semibold text-ink">{c.label}</span>
                <button
                  type="button"
                  onClick={async () => {
                    await accountApi.removeCar(c.id);
                    setState({ status: "ready", data: { ...state.data, cars: cars.filter((x) => x.id !== c.id) } });
                  }}
                  className="min-h-11 shrink-0 rounded-full px-3 font-bold text-orange-text underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
                  aria-label={`Remove ${c.label}`}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section id="history" title="Diagnosis history" icon={<History aria-hidden="true" className="size-6 text-orange-text" />}>
        {sessions.length === 0 ? (
          <p className="text-ink/80">
            No diagnoses yet.{" "}
            <Link href="/diagnose" className="font-bold text-orange-text underline underline-offset-4">
              Start one
            </Link>
          </p>
        ) : (
          <ul className="flex flex-col gap-2" data-testid="history">
            {sessions.map((s) => (
              <li key={s.session_id}>
                <Link
                  href={s.status === "completed" ? `/diagnose/${s.session_id}/result` : `/diagnose/${s.session_id}`}
                  className="flex min-h-14 flex-col rounded-2xl bg-warm-white p-3 outline-none hover:bg-[#ffe6d3] focus-visible:ring-3 focus-visible:ring-ring"
                >
                  <span className="font-bold text-ink">{s.top_cause ?? s.topic ?? "Diagnosis"}</span>
                  <span className="text-sm text-ink/75">
                    {s.vehicle} · {shortDate(s.created_at.slice(0, 10))} · {SESSION_STATUS[s.status]}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section id="requests" title="My requests" icon={<ClipboardList aria-hidden="true" className="size-6 text-orange-text" />}>
        {requests.length === 0 ? (
          <p className="text-ink/80">No mechanic requests yet.</p>
        ) : (
          <ul className="flex flex-col gap-2" data-testid="my-requests">
            {requests.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/requests/${r.id}`}
                  className="flex min-h-14 flex-col rounded-2xl bg-warm-white p-3 outline-none hover:bg-[#ffe6d3] focus-visible:ring-3 focus-visible:ring-ring"
                >
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-bold text-ink tabular-nums">{r.reference}</span>
                    <span className="rounded-full bg-ink/10 px-2 py-0.5 text-sm font-semibold text-ink">{r.status_label}</span>
                  </span>
                  <span className="text-sm text-ink/75">
                    {r.vehicle} · {shortDate(r.created_at.slice(0, 10))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <NotificationChoices />

      <section aria-labelledby="mydata-h" className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-5">
        <h2 id="mydata-h" className="text-xl font-black text-ink">
          My data
        </h2>
        <p className="text-ink/85">
          Download everything we keep about you as a file (JSON): your account, cars, diagnoses, requests, choices and
          consents.
        </p>
        <Link href="/privacy" className="inline-flex min-h-11 items-center self-start font-bold text-orange-text underline underline-offset-4">
          How we use your data: our privacy notice
        </Link>
        <a
          href={`${API_URL}/api/me/export`}
          data-testid="download-data"
          className="inline-flex h-12 items-center self-start rounded-full border-2 border-ink/15 px-6 text-base font-bold text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring"
        >
          Download my data
        </a>
      </section>

      <DeleteAccount onDeleted={() => setDeleted(true)} />
    </div>
  );
}
