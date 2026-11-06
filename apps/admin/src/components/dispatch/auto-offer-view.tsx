"use client";

import { useCallback, useState } from "react";

import { ErrorBox } from "@/components/error-box";
import { adminApi, type AutoOffer, type AutoOfferSwitch, errorMessage } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

/** Auto-offer on / off per zone and job type (super admins; each change is audited). */
export function AutoOfferView() {
  const { state, reload, set } = useLoad(useCallback((s: AbortSignal) => adminApi.autoOffer(s), []));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (state.kind === "loading") return <p role="status">Loading…</p>;
  if (state.kind === "error") return <ErrorBox message={state.message} onRetry={reload} />;
  const data: AutoOffer = state.data;
  const find = (zone: string, type: string) => data.switches.find((s) => s.zone === zone && s.service_type === type)!;

  async function flip(sw: AutoOfferSwitch) {
    const key = `${sw.zone}/${sw.service_type}`;
    setBusy(key);
    setError(null);
    try {
      set(await adminApi.setAutoOffer(sw.zone, sw.service_type, !sw.enabled));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-ink/80">
        An offer expires after {Math.round(data.offer_expiry_seconds / 60)} minutes; a request nobody accepts within{" "}
        {Math.round(data.escalate_seconds / 60)} minutes of its first offer is escalated to support (both for manual and
        automatic offers).
      </p>
      {error && <ErrorBox message={error} />}
      <div className="overflow-x-auto rounded-3xl border border-border bg-white p-4">
        <table className="w-full min-w-[36rem] text-left" data-testid="auto-offer">
          <caption className="sr-only">Auto-offer by zone and job type</caption>
          <thead>
            <tr className="text-sm text-ink/70">
              <th scope="col" className="py-2 pr-3 font-semibold">
                Zone
              </th>
              {data.job_types.map((j) => (
                <th key={j.code} scope="col" className="py-2 pr-3 font-semibold">
                  {j.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.zones.map((z) => (
              <tr key={z.code} className="border-t border-border">
                <th scope="row" className="py-3 pr-3 font-bold text-ink">
                  {z.label}
                </th>
                {data.job_types.map((j) => {
                  const sw = find(z.code, j.code);
                  return (
                    <td key={j.code} className="py-3 pr-3 align-top">
                      <button
                        type="button"
                        role="switch"
                        aria-checked={sw.enabled}
                        aria-label={`Auto-offer for ${j.label} in ${z.label}`}
                        disabled={busy !== null}
                        onClick={() => void flip(sw)}
                        className={`min-h-11 min-w-20 rounded-full px-4 font-bold outline-none focus-visible:ring-3 focus-visible:ring-ring ${
                          sw.enabled ? "bg-cta text-white" : "border-2 border-ink/20 bg-white text-ink"
                        }`}
                      >
                        {sw.enabled ? "On" : "Off"}
                      </button>
                      {sw.updated_at && (
                        <span className="mt-1 block text-xs text-ink/70">
                          {sw.updated_by} · {dateTime(sw.updated_at)}
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
