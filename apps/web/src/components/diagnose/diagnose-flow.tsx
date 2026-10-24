"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { CarFront } from "lucide-react";

import { ProblemStep } from "@/components/diagnose/problem-step";
import { VehicleStep } from "@/components/diagnose/vehicle-step";
import { Stepper } from "@/components/stepper";
import { Button } from "@/components/ui/button";
import { saveVehicle, SEGMENT_LABELS, useSavedVehicle, type VehicleChoice } from "@/lib/vehicle";

/** Steps 1 and 2 of the diagnosis: the car, then the problem (which starts the session and opens the questions). */
export function DiagnoseFlow() {
  const params = useSearchParams();
  const topic = params.get("topic");
  // Coming back from the questions (/diagnose?step=problem) reopens the Problem step for the saved car.
  const saved = useSavedVehicle();
  const [picked, setPicked] = useState<VehicleChoice | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const vehicle = picked ?? (params.get("step") === "problem" && !dismissed ? saved : null);

  const done = (choice: VehicleChoice) => {
    saveVehicle(choice);
    setPicked(choice);
    window.scrollTo({ top: 0 });
  };

  const changeCar = () => {
    setPicked(null);
    setDismissed(true);
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
        <section aria-labelledby="problem-heading" className="flex flex-col gap-6">
          <h1 id="problem-heading" className="text-4xl leading-tight font-black tracking-tight text-ink sm:text-5xl">
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
              onClick={changeCar}
            >
              Change car
            </Button>
          </div>
          <ProblemStep vehicle={vehicle} preselected={topic} />
        </section>
      )}
    </div>
  );
}
