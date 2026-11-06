import { TriangleAlert } from "lucide-react";

import type { SafetyAlert } from "@/lib/api";
import { informative, towingText } from "@/lib/format";

/** Safety alerts in red, most serious first. Shown the moment the API returns them. Always English (lang="en"), also
 * on the Hindi pages: safety text is never machine-translated, and no reviewed Hindi exists yet (Phase 5.5). */
export function SafetyBanner({ alerts, id }: { alerts: SafetyAlert[]; id?: string }) {
  if (!alerts.length) return null;
  const order = { high: 0, medium: 1, low: 2 } as const;
  const sorted = [...alerts].sort((a, b) => order[a.risk] - order[b.risk]);
  const stop = sorted[0].risk === "high";
  return (
    <section
      id={id}
      role="alert"
      lang="en"
      aria-labelledby={id ? `${id}-title` : undefined}
      className="rounded-3xl bg-danger p-5 text-white shadow-lg"
      data-testid="safety-banner"
    >
      <h2 id={id ? `${id}-title` : undefined} className="flex items-center gap-2 text-xl font-black">
        <TriangleAlert aria-hidden="true" className="size-6 shrink-0" />
        {stop ? "Safety first: stop and read this" : "Safety warning"}
      </h2>
      <ul className="mt-3 flex flex-col gap-3">
        {sorted.map((a) => {
          const action = informative(a.roadside_action);
          const trigger = informative(a.stop_driving_trigger);
          const towing = towingText(a.towing);
          return (
            <li key={a.rule_id} className="rounded-2xl bg-white/10 p-3">
              <p className="font-bold">{action || a.reason}</p>
              {trigger && trigger !== action && <p className="mt-1 text-white/95">{trigger}</p>}
              {towing && <p className="mt-1 text-white/95">Towing: {towing}</p>}
              {action && <p className="mt-1 text-sm text-white">Why: {a.reason}</p>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
