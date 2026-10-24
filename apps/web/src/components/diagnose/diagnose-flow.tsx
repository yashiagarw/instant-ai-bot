"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { CarFront } from "lucide-react";

import { VehicleStep } from "@/components/diagnose/vehicle-step";
import { Stepper } from "@/components/stepper";
import { Button } from "@/components/ui/button";
import { saveVehicle, SEGMENT_LABELS, type VehicleChoice } from "@/lib/vehicle";

/** The diagnosis wizard. Step 1 (Car) is built; the Problem step comes next. */
export function DiagnoseFlow() {
  const topic = useSearchParams().get("topic");
  const [vehicle, setVehicle] = useState<VehicleChoice | null>(null);

  const done = (choice: VehicleChoice) => {
    saveVehicle(choice);
    setVehicle(choice);
    window.scrollTo({ top: 0 });
  };

  return (
    <div className="flex flex-col gap-8">
      <Stepper current={vehicle ? "Problem" : "Car"} />
      {!vehicle && (
        <>
          <div>
            <h1 className="text-4xl leading-tight font-black tracking-tight text-ink sm:text-5xl">
              Which car do you drive?
            </h1>
            <p className="mt-2 text-lg text-ink/75">We use it to check parts and estimate costs for your car.</p>
          </div>
          <VehicleStep onDone={done} />
        </>
      )}
      {vehicle && (
        <section aria-labelledby="problem-heading" className="flex flex-col gap-5">
          <h1 id="problem-heading" tabIndex={-1} className="text-4xl leading-tight font-black tracking-tight text-ink sm:text-5xl">
            What&apos;s the problem?
          </h1>
          <div className="flex flex-col gap-3 rounded-3xl border-2 border-cta/40 bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="flex items-start gap-3 text-ink">
              <CarFront aria-hidden="true" className="mt-0.5 size-6 shrink-0 text-orange-text" />
              <span>
                <span className="block text-sm text-ink/70">Your car</span>
                <span className="block text-lg font-bold" data-testid="chosen-car">
                  {vehicle.label}
                </span>
                {vehicle.kind === "listed" && (
                  <span className="block text-sm text-ink/75">Price range: {SEGMENT_LABELS[vehicle.price_segment]}</span>
                )}
                {vehicle.kind === "unlisted" && (
                  <span className="block text-sm text-ink/75">
                    {vehicle.unlisted.price_segment
                      ? `Price range: ${SEGMENT_LABELS[vehicle.unlisted.price_segment]}`
                      : "Price range: not sure (we'll show general guidance)"}
                  </span>
                )}
              </span>
            </p>
            <Button
              type="button"
              variant="outline"
              className="h-12 border-2 border-ink/15 bg-white px-5 text-base font-semibold text-ink"
              onClick={() => setVehicle(null)}
            >
              Change car
            </Button>
          </div>
          <p className="rounded-2xl bg-white p-4 text-ink/80">
            Choosing the problem is the next step and is coming soon.
            {topic && <span className="sr-only"> Selected topic: {topic}.</span>}
          </p>
        </section>
      )}
    </div>
  );
}
