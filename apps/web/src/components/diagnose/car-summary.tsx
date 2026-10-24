import { CarFront } from "lucide-react";

import type { VehicleSummary } from "@/lib/api";
import { SEGMENT_LABELS } from "@/lib/vehicle";

/** The car (and topic) at the top of the questions and the result. */
export function CarSummary({ vehicle, topic }: { vehicle: VehicleSummary; topic?: string | null }) {
  return (
    <p className="flex items-center gap-3 text-ink" data-testid="car-summary">
      <CarFront aria-hidden="true" className="size-6 shrink-0 text-orange-text" />
      <span className="min-w-0">
        <span className="block truncate font-bold">{vehicle.label}</span>
        <span className="block truncate text-sm text-ink/70">
          {[topic, vehicle.price_segment ? SEGMENT_LABELS[vehicle.price_segment] : "Price range unknown"]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </span>
    </p>
  );
}
