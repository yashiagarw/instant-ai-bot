import { BadgeCheck, CircleHelp, Gauge } from "lucide-react";

import type { CoverageLevel } from "@/lib/api";
import { cn } from "@/lib/utils";

export const COVERAGE: Record<CoverageLevel, { label: string; explain: string; className: string; Icon: typeof Gauge }> = {
  part_fit_verified: {
    label: "Part fit verified",
    explain: "The parts and prices were checked for your exact model.",
    className: "bg-success-bg text-success border-success/30",
    Icon: BadgeCheck,
  },
  segment_estimate: {
    label: "Segment estimate",
    explain: "Costs are typical for cars in your price range, not checked for your exact model.",
    className: "bg-warm-white text-orange-text border-orange-text/30",
    Icon: Gauge,
  },
  general_guidance: {
    label: "General guidance",
    explain: "General advice only: we don't know enough about your car to estimate costs.",
    className: "bg-amber-bg text-amber-text border-amber-text/30",
    Icon: CircleHelp,
  },
};

export function CoverageBadge({ level }: { level: CoverageLevel }) {
  const c = COVERAGE[level];
  return (
    <div className="flex flex-col gap-1.5" data-testid="coverage">
      <span
        className={cn("inline-flex items-center gap-1.5 self-start rounded-full border px-3 py-1 text-sm font-bold", c.className)}
      >
        <c.Icon aria-hidden="true" className="size-4" />
        {c.label}
      </span>
      <p className="text-sm text-ink/75">{c.explain}</p>
    </div>
  );
}
