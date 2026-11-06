"use client";

import { CarFront } from "lucide-react";
import { useTranslations } from "next-intl";

import type { VehicleSummary } from "@/lib/api";
import { useVehicleLabels } from "@/lib/use-vehicle-labels";

/** The car (and topic) at the top of the questions and the result. */
export function CarSummary({ vehicle, topic }: { vehicle: VehicleSummary; topic?: string | null }) {
  const t = useTranslations("common");
  const labels = useVehicleLabels();
  return (
    <p className="flex items-center gap-3 text-ink" data-testid="car-summary">
      <CarFront aria-hidden="true" className="size-6 shrink-0 text-orange-text" />
      <span className="min-w-0">
        <span className="block truncate font-bold">{vehicle.label}</span>
        <span className="block truncate text-sm text-ink/70">
          {[topic, vehicle.price_segment ? labels.segment(vehicle.price_segment) : t("priceUnknown")]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </span>
    </p>
  );
}
