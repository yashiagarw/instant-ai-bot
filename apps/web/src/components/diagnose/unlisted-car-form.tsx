"use client";

import { type FormEvent, useId, useState } from "react";

import { ChoiceGroup } from "@/components/choice-group";
import { Button } from "@/components/ui/button";
import type { Fuel, PriceSegment, Transmission } from "@/lib/api";
import { FUEL_LABELS, SEGMENT_LABELS, TRANSMISSION_LABELS, type VehicleChoice } from "@/lib/vehicle";

const UNSURE = "unsure";
type Unsure = typeof UNSURE;

const FUELS: { value: Fuel | Unsure; label: string }[] = [
  ...(Object.entries(FUEL_LABELS) as [Fuel, string][]).map(([value, label]) => ({ value, label })),
  { value: UNSURE, label: "Not sure" },
];
const TRANSMISSIONS: { value: Transmission | Unsure; label: string }[] = [
  ...(Object.entries(TRANSMISSION_LABELS) as [Transmission, string][]).map(([value, label]) => ({ value, label })),
  { value: UNSURE, label: "Not sure" },
];
const SEGMENTS: { value: PriceSegment | Unsure; label: string }[] = [
  ...(Object.entries(SEGMENT_LABELS) as [PriceSegment, string][]).map(([value, label]) => ({ value, label })),
  { value: UNSURE, label: "Not sure" },
];

const MIN_YEAR = 1980;

interface Errors {
  make?: string;
  model?: string;
  year?: string;
  fuel?: string;
  transmission?: string;
  segment?: string;
}

function TextField({
  label,
  value,
  onChange,
  error,
  ...input
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
} & Omit<React.ComponentProps<"input">, "value" | "onChange">) {
  const id = useId();
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-lg font-bold text-ink">
        {label}
      </label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className="h-14 rounded-full border-2 border-ink/15 bg-white px-5 text-lg text-ink outline-none focus-visible:border-cta focus-visible:ring-3 focus-visible:ring-ring/40 aria-invalid:border-orange-text"
        {...input}
      />
      {error && (
        <p id={`${id}-error`} className="text-sm font-semibold text-orange-text">
          {error}
        </p>
      )}
    </div>
  );
}

/** Make, model and year typed in; fuel, transmission and rough price picked. Saved to unlisted_vehicles by the
 * API when the diagnosis starts. */
export function UnlistedCarForm({ onDone, onCancel }: { onDone: (c: VehicleChoice) => void; onCancel: () => void }) {
  const maxYear = new Date().getFullYear() + 1;
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const [fuel, setFuel] = useState<Fuel | Unsure>();
  const [transmission, setTransmission] = useState<Transmission | Unsure>();
  const [segment, setSegment] = useState<PriceSegment | Unsure>();
  const [errors, setErrors] = useState<Errors>({});

  function submit(e: FormEvent) {
    e.preventDefault();
    const y = Number(year);
    const next: Errors = {
      make: make.trim() ? undefined : "Type the make, for example Maruti Suzuki.",
      model: model.trim() ? undefined : "Type the model, for example Gypsy.",
      year:
        Number.isInteger(y) && y >= MIN_YEAR && y <= maxYear
          ? undefined
          : `Type the year as 4 digits, between ${MIN_YEAR} and ${maxYear}.`,
      fuel: fuel ? undefined : "Pick a fuel, or Not sure.",
      transmission: transmission ? undefined : "Pick a gearbox, or Not sure.",
      segment: segment ? undefined : "Pick a price range, or Not sure.",
    };
    setErrors(next);
    if (Object.values(next).some(Boolean)) {
      // Move focus to the first field that needs fixing, once the error messages have rendered.
      const form = e.currentTarget as HTMLFormElement;
      requestAnimationFrame(() =>
        form.querySelector<HTMLElement>('[aria-invalid="true"], fieldset[aria-describedby] input')?.focus(),
      );
      return;
    }
    const unlisted = {
      make: make.trim(),
      model: model.trim(),
      year: y,
      fuel: fuel === UNSURE ? null : fuel!,
      transmission: transmission === UNSURE ? null : transmission!,
      price_segment: segment === UNSURE ? null : segment!,
    };
    onDone({ kind: "unlisted", unlisted, label: `${unlisted.make} ${unlisted.model} ${y}` });
  }

  return (
    <form onSubmit={submit} noValidate aria-labelledby="unlisted-heading" className="flex flex-col gap-7">
      <div>
        <h2 id="unlisted-heading" className="text-2xl font-black tracking-tight text-ink">
          Tell us about your car
        </h2>
        <p className="mt-1 text-ink/75">We&apos;ll still help. Your answers help us add more cars.</p>
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField label="Make" value={make} onChange={setMake} error={errors.make} autoComplete="off" maxLength={60} />
        <TextField label="Model" value={model} onChange={setModel} error={errors.model} autoComplete="off" maxLength={60} />
        <TextField
          label="Year"
          value={year}
          onChange={setYear}
          error={errors.year}
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={4}
          placeholder="e.g. 2015"
        />
      </div>
      <ChoiceGroup legend="Fuel" choices={FUELS} value={fuel} onChange={setFuel} error={errors.fuel} />
      <ChoiceGroup
        legend="Gearbox"
        choices={TRANSMISSIONS}
        value={transmission}
        onChange={setTransmission}
        error={errors.transmission}
      />
      <ChoiceGroup
        legend="Roughly what did the car cost new?"
        choices={SEGMENTS}
        value={segment}
        onChange={setSegment}
        columns="grid-cols-1 sm:grid-cols-2"
        error={errors.segment}
      />
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="submit" size="cta">
          Continue
        </Button>
        <Button type="button" size="cta" variant="outline" className="border-2 border-ink/15 bg-white text-ink" onClick={onCancel}>
          Back to the car list
        </Button>
      </div>
    </form>
  );
}
