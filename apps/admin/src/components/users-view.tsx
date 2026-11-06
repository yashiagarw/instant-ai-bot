"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Copy, Eye, UserPlus } from "lucide-react";

import { Button } from "@im/ui/button";
import { cn } from "@im/ui/cn";
import { type ColumnDef, DataTable } from "@im/ui/data-table";
import { Dialog } from "@im/ui/dialog";
import { ErrorBox } from "@/components/error-box";
import { Field } from "@/components/field";
import { useMe } from "@/components/staff-shell";
import { adminApi, type Customer, errorMessage, type Role, ROLES, roleLabel, type Staff } from "@/lib/api";
import { date, dateTime, staffStatus } from "@/lib/format";

type Load<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T };

function useList<T>(fetcher: ((signal: AbortSignal) => Promise<T[]>) | null) {
  const [state, setState] = useState<Load<T[]>>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!fetcher) return;
    const ctrl = new AbortController();
    fetcher(ctrl.signal)
      .then((data) => setState({ kind: "ready", data }))
      .catch((e) => !ctrl.signal.aborted && setState({ kind: "error", message: errorMessage(e) }));
    return () => ctrl.abort();
  }, [fetcher, attempt]);
  const reload = useCallback(() => setAttempt((a) => a + 1), []);
  return { state, setState, reload };
}

/** Staff (staff.read) and customers (customers.read), each in its own tab. */
export function UsersView() {
  const { me } = useMe();
  const tabs = [
    me.permissions.includes("staff.read") && { key: "staff", label: "Staff" },
    me.permissions.includes("customers.read") && { key: "customers", label: "Customers" },
  ].filter(Boolean) as { key: string; label: string }[];
  const [tab, setTab] = useState(tabs[0]?.key);

  return (
    <div className="flex flex-col gap-4">
      {tabs.length > 1 && (
        <div role="tablist" aria-label="Users" className="flex gap-2">
          {tabs.map((t) => (
            <button
              key={t.key}
              role="tab"
              type="button"
              id={`tab-${t.key}`}
              aria-selected={tab === t.key}
              aria-controls={`panel-${t.key}`}
              onClick={() => setTab(t.key)}
              className={cn(
                "min-h-11 rounded-full border-2 px-5 font-bold outline-none focus-visible:ring-3 focus-visible:ring-ring",
                tab === t.key ? "border-ink bg-ink text-white" : "border-border bg-white text-ink",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}
      <div role={tabs.length > 1 ? "tabpanel" : undefined} id={`panel-${tab}`} aria-labelledby={tabs.length > 1 ? `tab-${tab}` : undefined}>
        {tab === "staff" ? <StaffTable /> : <CustomerTable />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- staff

function StaffTable() {
  const { me } = useMe();
  const manage = me.permissions.includes("staff.manage");
  const { state, setState, reload } = useList(adminApi.staff);
  const [inviting, setInviting] = useState(false);
  const [editing, setEditing] = useState<Staff | null>(null);
  const [confirm, setConfirm] = useState<{ staff: Staff; action: "deactivate" | "reset" } | null>(null);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");

  const replace = useCallback(
    (s: Staff) =>
      setState((st) => (st.kind === "ready" ? { kind: "ready", data: st.data.map((x) => (x.id === s.id ? s : x)) } : st)),
    [setState],
  );

  const act = useCallback(
    async (fn: () => Promise<Staff>, done: string) => {
      setActionError("");
      try {
        const s = await fn();
        replace(s);
        setNotice(done);
      } catch (e) {
        setActionError(errorMessage(e));
      }
    },
    [replace],
  );

  const columns = useMemo<ColumnDef<Staff, unknown>[]>(
    () => [
      {
        id: "name",
        accessorFn: (s) => `${s.name} ${s.email}`, // so the search finds people by email too
        header: "Name",
        cell: ({ row }) => (
          <span className="flex flex-col">
            <span className="font-bold">{row.original.name}</span>
            <span className="text-ink/75">{row.original.email}</span>
          </span>
        ),
      },
      {
        accessorKey: "roles",
        header: "Roles",
        enableSorting: false,
        cell: ({ row }) => (
          <span className="flex flex-wrap gap-1">
            {row.original.roles.map((r) => (
              <span key={r} className="rounded-full bg-warm-white px-2 py-0.5 text-xs font-bold whitespace-nowrap">
                {roleLabel(r)}
              </span>
            ))}
          </span>
        ),
      },
      { id: "status", accessorFn: staffStatus, header: "Status" },
      { id: "last", accessorFn: (s) => s.last_login_at ?? "", header: "Last sign-in", cell: ({ row }) => dateTime(row.original.last_login_at) },
      ...(manage
        ? [
            {
              id: "actions",
              header: "Actions",
              enableSorting: false,
              cell: ({ row }: { row: { original: Staff } }) => {
                const s = row.original;
                const self = s.id === me.id;
                return (
                  <span className="flex flex-wrap gap-1">
                    <Small onClick={() => setEditing(s)}>Roles</Small>
                    {s.active ? (
                      !self && <Small onClick={() => setConfirm({ staff: s, action: "deactivate" })}>Disable</Small>
                    ) : (
                      <Small onClick={() => void act(() => adminApi.activate(s.id), `${s.name} can sign in again.`)}>Enable</Small>
                    )}
                    {s.locked && <Small onClick={() => void act(() => adminApi.unlock(s.id), `${s.name} is unlocked.`)}>Unlock</Small>}
                    {s.two_factor && !self && <Small onClick={() => setConfirm({ staff: s, action: "reset" })}>Reset two-factor</Small>}
                  </span>
                );
              },
            } satisfies ColumnDef<Staff, unknown>,
          ]
        : []),
    ],
    [manage, me.id, act],
  );

  if (state.kind === "loading") return <p role="status">Loading staff…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;

  return (
    <section aria-labelledby="staff-h" className="flex flex-col gap-3">
      <h2 id="staff-h" className="sr-only">Staff</h2>
      <p aria-live="polite" className="text-sm font-semibold text-ink" data-testid="staff-notice">
        {notice}
      </p>
      {actionError && <ErrorBox message={actionError} />}
      <DataTable
        data={state.data}
        columns={columns}
        caption="Staff accounts"
        searchLabel="Search staff"
        filters={[
          { column: "roles", label: "Role", options: ROLES.map((r) => ({ value: r.value, label: r.label })) },
          { column: "status", label: "Status" },
        ]}
        csv={{
          filename: "staff",
          columns: [
            { header: "Name", value: (s) => s.name },
            { header: "Email", value: (s) => s.email },
            { header: "Roles", value: (s) => s.roles.map(roleLabel) },
            { header: "Status", value: staffStatus },
            { header: "Last sign-in", value: (s) => s.last_login_at ?? "" },
          ],
        }}
        getRowId={(s) => s.id}
        actions={
          manage && (
            <Button type="button" className="h-11 rounded-full px-5 text-base font-bold" onClick={() => setInviting(true)}>
              <UserPlus aria-hidden="true" className="size-5" />
              Invite staff
            </Button>
          )
        }
      />
      {manage && (
        <>
          <InviteDialog
            open={inviting}
            onOpenChange={setInviting}
            onInvited={(s) => setState((st) => (st.kind === "ready" ? { kind: "ready", data: [...st.data, s] } : st))}
          />
          {editing && (
            <RolesDialog
              staff={editing}
              onClose={() => setEditing(null)}
              onSaved={(s) => {
                replace(s);
                setNotice(`Roles saved for ${s.name}. They were signed out to pick up the change.`);
              }}
            />
          )}
          <Dialog
            open={confirm !== null}
            onOpenChange={(o) => !o && setConfirm(null)}
            title={confirm?.action === "reset" ? "Reset two-factor?" : "Disable this account?"}
            description={
              confirm?.action === "reset"
                ? `${confirm.staff.name} is signed out and sets up two-factor again (new QR code) at their next sign-in. Use this when they lost their phone.`
                : `${confirm?.staff.name} is signed out and can't sign in until enabled again. Nothing is deleted.`
            }
          >
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                className="h-11 rounded-full px-5 text-base font-bold"
                onClick={() => {
                  const c = confirm!;
                  setConfirm(null);
                  void (c.action === "reset"
                    ? act(() => adminApi.resetTwoFactor(c.staff.id), `Two-factor reset for ${c.staff.name}.`)
                    : act(() => adminApi.deactivate(c.staff.id), `${c.staff.name} is disabled.`));
                }}
              >
                {confirm?.action === "reset" ? "Reset two-factor" : "Disable account"}
              </Button>
              <Button type="button" variant="outline" className="h-11 rounded-full px-5 text-base" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
            </div>
          </Dialog>
        </>
      )}
    </section>
  );
}

function Small({ children, onClick }: { children: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="min-h-11 rounded-full border border-border px-3 text-sm font-semibold whitespace-nowrap text-ink outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
    >
      {children}
    </button>
  );
}

function RoleChecks({ value, onChange }: { value: Role[]; onChange: (roles: Role[]) => void }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 font-semibold text-ink">Roles</legend>
      {ROLES.map((r) => (
        <label key={r.value} className="flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border border-border p-3">
          <input
            type="checkbox"
            className="mt-1 size-5 accent-cta"
            checked={value.includes(r.value)}
            onChange={(e) => onChange(e.target.checked ? [...value, r.value] : value.filter((x) => x !== r.value))}
          />
          <span>
            <span className="block font-bold text-ink">{r.label}</span>
            <span className="text-sm text-ink/75">{r.description}</span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}

function InviteDialog({
  open,
  onOpenChange,
  onInvited,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onInvited: (s: Staff) => void;
}) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<{ staff: Staff; password: string } | null>(null);
  const [copied, setCopied] = useState(false);

  function close(o: boolean) {
    if (!o) {
      setDone(null); // the temporary password is gone once the dialog closes
      setRoles([]);
      setError("");
      setCopied(false);
    }
    onOpenChange(o);
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (!roles.length) {
      setError("Choose at least one role.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const r = await adminApi.invite(String(f.get("email")), String(f.get("name")), roles);
      setDone({ staff: r.staff, password: r.temporary_password });
      onInvited(r.staff);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close} title={done ? "Staff invited" : "Invite staff"}>
      {done ? (
        <div className="flex flex-col gap-3" data-testid="invite-done">
          <p className="text-ink">
            Give <strong>{done.staff.name}</strong> this temporary password in person or by phone. It is shown only
            now.
          </p>
          <p className="flex flex-wrap items-center gap-2 rounded-2xl bg-warm-white p-3">
            <code className="font-mono text-lg font-bold break-all" data-testid="temporary-password">
              {done.password}
            </code>
            <button
              type="button"
              onClick={() => void navigator.clipboard?.writeText(done.password).then(() => setCopied(true))}
              className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 font-semibold text-orange-text"
            >
              <Copy aria-hidden="true" className="size-4" />
              {copied ? "Copied" : "Copy"}
            </button>
          </p>
          <p className="text-sm text-ink/80">
            They sign in at this admin app with {done.staff.email}, set up two-factor (a QR code for Google
            Authenticator), then choose their own password.
          </p>
          <Button type="button" className="h-11 self-start rounded-full px-5 text-base font-bold" onClick={() => close(false)}>
            Done
          </Button>
        </div>
      ) : (
        <form method="post" onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <Field label="Name" name="name" required autoComplete="off" />
          <Field label="Work email" name="email" type="email" required autoComplete="off" />
          <RoleChecks value={roles} onChange={setRoles} />
          {error && (
            <p role="alert" className="font-semibold text-orange-text">
              {error}
            </p>
          )}
          <Button type="submit" size="cta" disabled={busy}>
            {busy ? "Inviting…" : "Invite"}
          </Button>
        </form>
      )}
    </Dialog>
  );
}

function RolesDialog({ staff, onClose, onSaved }: { staff: Staff; onClose: () => void; onSaved: (s: Staff) => void }) {
  const [roles, setRoles] = useState<Role[]>(staff.roles);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setBusy(true);
    setError("");
    try {
      onSaved(await adminApi.setRoles(staff.id, roles));
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={`Roles for ${staff.name}`} description="They are signed out so the new roles apply at their next sign-in.">
      <RoleChecks value={roles} onChange={setRoles} />
      {error && (
        <p role="alert" className="font-semibold text-orange-text">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="button" className="h-11 rounded-full px-5 text-base font-bold" disabled={busy || !roles.length} onClick={() => void save()}>
          {busy ? "Saving…" : "Save roles"}
        </Button>
        <Button type="button" variant="outline" className="h-11 rounded-full px-5 text-base" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------- customers

function CustomerTable() {
  const { me } = useMe();
  const contact = me.permissions.includes("customers.contact");
  const { state, reload } = useList(adminApi.customers);
  const [shown, setShown] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  const reveal = useCallback(async (c: Customer) => {
    setError("");
    try {
      const { phone } = await adminApi.revealPhone(c.id);
      setShown((s) => ({ ...s, [c.id]: phone }));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  const columns = useMemo<ColumnDef<Customer, unknown>[]>(
    () => [
      { id: "name", accessorFn: (c) => c.name ?? "", header: "Name", cell: ({ row }) => row.original.name || "No name" },
      {
        accessorKey: "phone_masked",
        header: "Phone",
        enableSorting: false,
        cell: ({ row }) => {
          const c = row.original;
          return (
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-mono tabular-nums">{shown[c.id] ?? c.phone_masked}</span>
              {contact && !shown[c.id] && (
                <button
                  type="button"
                  onClick={() => void reveal(c)}
                  aria-label={`Show full number for ${c.name || "this customer"}`}
                  className="inline-flex min-h-11 items-center gap-1 rounded-full px-2 text-sm font-semibold text-orange-text outline-none focus-visible:ring-3 focus-visible:ring-ring"
                >
                  <Eye aria-hidden="true" className="size-4" />
                  Show
                </button>
              )}
            </span>
          );
        },
      },
      { id: "joined", accessorFn: (c) => c.created_at, header: "Joined", cell: ({ row }) => date(row.original.created_at) },
      { id: "last", accessorFn: (c) => c.last_login_at ?? "", header: "Last sign-in", cell: ({ row }) => dateTime(row.original.last_login_at) },
      { accessorKey: "diagnoses", header: "Diagnoses" },
      { accessorKey: "requests", header: "Requests" },
    ],
    [contact, shown, reveal],
  );

  if (state.kind === "loading") return <p role="status">Loading customers…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  return (
    <section aria-labelledby="customers-h" className="flex flex-col gap-3">
      <h2 id="customers-h" className="sr-only">Customers</h2>
      <p className="text-sm text-ink/80">
        Phone numbers are hidden.{" "}
        {contact ? "Show one only when you need to call that customer; each time is recorded in the audit log." : "Your role can't see full numbers."}
      </p>
      {error && <ErrorBox message={error} />}
      <DataTable
        data={state.data}
        columns={columns}
        caption="Customer accounts"
        searchLabel="Search customers (name or last digits)"
        csv={{
          filename: "customers",
          columns: [
            { header: "Name", value: (c) => c.name ?? "" },
            { header: "Phone (masked)", value: (c) => c.phone_masked }, // never the revealed number
            { header: "Joined", value: (c) => c.created_at },
            { header: "Last sign-in", value: (c) => c.last_login_at ?? "" },
            { header: "Diagnoses", value: (c) => c.diagnoses },
            { header: "Requests", value: (c) => c.requests },
          ],
        }}
        getRowId={(c) => c.id}
        empty="No customers match."
      />
    </section>
  );
}
