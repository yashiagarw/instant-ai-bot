"use client";

import { type FormEvent, useState } from "react";
import { useTranslations } from "next-intl";

import { ChoiceGroup } from "@/components/choice-group";
import { TextField } from "@/components/text-field";
import { Button } from "@/components/ui/button";
import type { Fuel, PriceSegment, Transmission } from "@/lib/api";
import { useVehicleLabels } from "@/lib/use-vehicle-labels";
import { FUEL_LABELS, SEGMENT_LABELS, TRANSMISSION_LABELS, type VehicleChoice } from "@/lib/vehicle";

const UNSURE = "unsure";
type Unsure = typeof UNSURE;

const FUEL_KEYS = Object.keys(FUEL_LABELS) as Fuel[];
const TRANSMISSION_KEYS = Object.keys(TRANSMISSION_LABELS) as Transmission[];
const SEGMENT_KEYS = Object.keys(SEGMENT_LABELS) as PriceSegment[];

const MIN_YEAR = 1980;

interface Errors {
  make?: string;
  model?: string;
  year?: string;
  fuel?: string;
  transmission?: string;
  segment?: string;
}

/** Make, model and year typed in; fuel, transmission and rough price picked. Saved to unlisted_vehicles by the
 * API when the diagnosis starts. */
export function UnlistedCarForm({ onDone, onCancel }: { onDone: (c: VehicleChoice) => void; onCancel: () => void }) {
  const t = useTranslations("diagnose");
  const tc = useTranslations("common");
  const labels = useVehicleLabels();
  const notSure = { value: UNSURE, label: tc("notSure") } as const;
  const FUELS: { value: Fuel | Unsure; label: string }[] = [
    ...FUEL_KEYS.map((value) => ({ value, label: labels.fuel(value) })),
    notSure,
  ];
  const TRANSMISSIONS: { value: Transmission | Unsure; label: string }[] = [
    ...TRANSMISSION_KEYS.map((value) => ({ value, label: labels.transmission(value) })),
    notSure,
  ];
  const SEGMENTS: { value: PriceSegment | Unsure; label: string }[] = [
    ...SEGMENT_KEYS.map((value) => ({ value, label: labels.segment(value) })),
    notSure,
  ];
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
      make: make.trim() ? undefined : t("errMake"),
      model: model.trim() ? undefined : t("errModel"),
      year:
        Number.isInteger(y) && y >= MIN_YEAR && y <= maxYear
          ? undefined
          : t("errYear", { min: MIN_YEAR, max: maxYear }),
      fuel: fuel ? undefined : t("errFuel"),
      transmission: transmission ? undefined : t("errGearbox"),
      segment: segment ? undefined : t("errSegment"),
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
          {t("unlistedTitle")}
        </h2>
        <p className="mt-1 text-ink/75">{t("unlistedText")}</p>
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField label={t("make")} value={make} onChange={setMake} error={errors.make} autoComplete="off" maxLength={60} />
        <TextField label={t("model")} value={model} onChange={setModel} error={errors.model} autoComplete="off" maxLength={60} />
        <TextField
          label={t("year")}
          value={year}
          onChange={setYear}
          error={errors.year}
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={4}
          placeholder={t("yearPlaceholder")}
        />
      </div>
      <ChoiceGroup legend={t("fuel")} choices={FUELS} value={fuel} onChange={setFuel} error={errors.fuel} />
      <ChoiceGroup
        legend={t("gearbox")}
        choices={TRANSMISSIONS}
        value={transmission}
        onChange={setTransmission}
        error={errors.transmission}
      />
      <ChoiceGroup
        legend={t("pricePaid")}
        choices={SEGMENTS}
        value={segment}
        onChange={setSegment}
        columns="grid-cols-1 sm:grid-cols-2"
        error={errors.segment}
      />
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="submit" size="cta">
          {tc("continue")}
        </Button>
        <Button type="button" size="cta" variant="outline" className="border-2 border-ink/15 bg-white text-ink" onClick={onCancel}>
          {t("backToList")}
        </Button>
      </div>
    </form>
  );
}
