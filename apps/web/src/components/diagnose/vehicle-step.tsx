"use client";

import { useState } from "react";
import { CarFront, Check } from "lucide-react";
import { useTranslations } from "next-intl";

import { ChoiceGroup } from "@/components/choice-group";
import { UnlistedCarForm } from "@/components/diagnose/unlisted-car-form";
import { VehicleSearch } from "@/components/diagnose/vehicle-search";
import { ErrorMessage } from "@/components/error-message";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { api, type Fuel, type Make, type Model, type Transmission, type Variant } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";
import { useVehicleLabels } from "@/lib/use-vehicle-labels";
import { matching, splitMakes, unique, type VehicleChoice, yearsOf } from "@/lib/vehicle";

function TileSkeletons({ count, label }: { count: number; label: string }) {
  return (
    <div aria-busy="true">
      <span role="status" className="sr-only">
        {label}
      </span>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {Array.from({ length: count }, (_, i) => (
          <Skeleton key={i} className="h-12 rounded-full" />
        ))}
      </div>
    </div>
  );
}

/** A finished pick shown as a summary with a Change button. */
function Picked({ label, value, onChange }: { label: string; value: string; onChange: () => void }) {
  const t = useTranslations("diagnose");
  const tc = useTranslations("common");
  return (
    <div className="flex min-h-14 items-center justify-between gap-3 rounded-full border-2 border-cta/40 bg-white py-1.5 pr-1.5 pl-5">
      <p className="text-ink">
        <span className="text-ink/70">{label}: </span>
        <span className="font-bold">{value}</span>
      </p>
      <Button
        type="button"
        variant="ghost"
        aria-label={t("changeField", { field: label.toLowerCase() })}
        className="h-11 px-4 text-base font-semibold text-orange-text"
        onClick={onChange}
      >
        {tc("change")}
      </Button>
    </div>
  );
}

function MakeTiles({ makes, onPick }: { makes: Make[]; onPick: (m: Make) => void }) {
  const t = useTranslations("diagnose");
  const [showAll, setShowAll] = useState(false);
  const { popular, others } = splitMakes(makes);
  const shown = showAll ? [...popular, ...others] : popular;
  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-bold text-ink">{t("pickMake")}</h2>
      <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {shown.map((m) => (
          <li key={m.id}>
            <button
              type="button"
              onClick={() => onPick(m)}
              className="flex min-h-14 w-full items-center justify-center rounded-full border-2 border-ink/15 bg-white px-3 text-base font-bold text-ink outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring"
            >
              {m.name}
            </button>
          </li>
        ))}
      </ul>
      {others.length > 0 && !showAll && (
        <Button
          type="button"
          variant="outline"
          className="h-12 self-start border-2 border-ink/15 bg-white px-5 text-base font-semibold"
          onClick={() => setShowAll(true)}
        >
          {t("moreMakes", { count: others.length })}
        </Button>
      )}
    </div>
  );
}

interface Selection {
  make?: Make;
  model?: Model;
  year?: number;
  fuel?: Fuel;
  transmission?: Transmission;
  variantId?: number;
}

/** Step 1: search, or make → model → year → fuel → gearbox (→ version). "My car isn't listed" opens a form. */
export function VehicleStep({ onDone }: { onDone: (choice: VehicleChoice) => void }) {
  const t = useTranslations("diagnose");
  const labels = useVehicleLabels();
  const [unlisted, setUnlisted] = useState(false);
  const [sel, setSel] = useState<Selection>({});
  const makes = useLoad("makes", (s) => api.makes(s));
  const models = useLoad(sel.make ? `make:${sel.make.id}` : null, (s) => api.models(sel.make!.id, s));
  const variants = useLoad(sel.model ? `model:${sel.model.id}` : null, (s) => api.variants(sel.model!.id, s));

  if (unlisted) {
    return <UnlistedCarForm onDone={onDone} onCancel={() => setUnlisted(false)} />;
  }

  // Choices left after each pick; a question with a single possible answer is answered for the customer.
  const all = sel.model && variants.state.status === "ready" ? variants.state.data : [];
  const years = yearsOf(all);
  const year = sel.year ?? (years.length === 1 ? years[0] : undefined);
  const fuels = year === undefined ? [] : unique(matching(all, { year }).map((v) => v.fuel));
  const fuel = sel.fuel ?? (fuels.length === 1 ? fuels[0] : undefined);
  const gears = fuel === undefined ? [] : unique(matching(all, { year, fuel }).map((v) => v.transmission));
  const transmission = sel.transmission ?? (gears.length === 1 ? gears[0] : undefined);
  const versions: Variant[] = transmission === undefined ? [] : matching(all, { year, fuel, transmission });
  const variant =
    versions.find((v) => v.id === sel.variantId) ?? (versions.length === 1 ? versions[0] : undefined);

  const finish = () => {
    if (!sel.make || !sel.model || !variant) return;
    onDone({
      kind: "listed",
      variant_id: variant.id,
      price_segment: variant.price_segment,
      label: `${sel.make.name} ${sel.model.name} ${year} · ${variant.name}`,
    });
  };

  return (
    <div className="flex flex-col gap-8">
      {!sel.make && (
        <>
          <VehicleSearch
            onPick={(h) =>
              onDone({
                kind: "listed",
                variant_id: h.variant_id,
                price_segment: h.price_segment,
                label: `${h.make} ${h.model} · ${h.variant}`,
              })
            }
          />
          {makes.state.status === "loading" && <TileSkeletons count={8} label={t("loadingMakes")} />}
          {makes.state.status === "error" && <ErrorMessage message={makes.state.message} onRetry={makes.retry} />}
          {makes.state.status === "ready" && <MakeTiles makes={makes.state.data} onPick={(make) => setSel({ make })} />}
        </>
      )}

      {sel.make && <Picked label={t("make")} value={sel.make.name} onChange={() => setSel({})} />}

      {sel.make && !sel.model && (
        <div className="flex flex-col gap-3">
          <h2 className="text-lg font-bold text-ink">{t("whichModel", { make: sel.make.name })}</h2>
          {models.state.status === "loading" && <TileSkeletons count={6} label={t("loadingModels")} />}
          {models.state.status === "error" && <ErrorMessage message={models.state.message} onRetry={models.retry} />}
          {models.state.status === "ready" && (
            <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              {models.state.data.map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    onClick={() => setSel({ make: sel.make, model: m })}
                    className="flex min-h-14 w-full items-center justify-center rounded-full border-2 border-ink/15 bg-white px-3 text-base font-bold text-ink outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring"
                  >
                    {m.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {sel.model && <Picked label={t("model")} value={sel.model.name} onChange={() => setSel({ make: sel.make })} />}

      {sel.model && variants.state.status === "loading" && <TileSkeletons count={8} label={t("loadingYears")} />}
      {sel.model && variants.state.status === "error" && (
        <ErrorMessage message={variants.state.message} onRetry={variants.retry} />
      )}

      {sel.model && variants.state.status === "ready" && (
        <>
          <ChoiceGroup
            legend={t("year")}
            choices={years.map((y) => ({ value: y, label: String(y) }))}
            value={year}
            onChange={(y) => setSel({ make: sel.make, model: sel.model, year: y })}
            columns="grid-cols-3 sm:grid-cols-5"
          />
          {year !== undefined && (
            <ChoiceGroup
              legend={t("fuel")}
              choices={fuels.map((f) => ({ value: f, label: labels.fuel(f) }))}
              value={fuel}
              onChange={(f) => setSel({ make: sel.make, model: sel.model, year, fuel: f })}
            />
          )}
          {fuel !== undefined && (
            <ChoiceGroup
              legend={t("gearbox")}
              choices={gears.map((g) => ({ value: g, label: labels.transmission(g) }))}
              value={transmission}
              onChange={(g) => setSel({ make: sel.make, model: sel.model, year, fuel, transmission: g })}
            />
          )}
          {versions.length > 1 && (
            <ChoiceGroup
              legend={t("whichVersion")}
              choices={versions.map((v) => ({ value: v.id, label: v.name, hint: v.engine || undefined }))}
              value={variant?.id}
              onChange={(id) => setSel({ ...sel, year, fuel, transmission, variantId: id })}
              columns="grid-cols-1 sm:grid-cols-2"
            />
          )}
        </>
      )}

      {variant && sel.make && sel.model && (
        <div className="flex flex-col gap-4 rounded-3xl border-2 border-cta bg-white p-5" aria-live="polite">
          <p className="flex items-start gap-3 text-ink">
            <CarFront aria-hidden="true" className="mt-0.5 size-6 shrink-0 text-orange-text" />
            <span>
              <span className="block text-lg font-bold">
                {sel.make.name} {sel.model.name} {year}
              </span>
              <span className="block text-ink/75">
                {variant.name} · {labels.fuel(variant.fuel)} · {labels.transmission(variant.transmission)}
              </span>
              <span className="mt-1 block text-sm text-ink/75">
                {t("priceForEstimates", { range: labels.segment(variant.price_segment) })}
              </span>
            </span>
          </p>
          <Button type="button" size="cta" onClick={finish} className="self-stretch sm:self-start">
            <Check aria-hidden="true" className="size-5" />
            {t("thisIsMyCar")}
          </Button>
        </div>
      )}

      <div className={cn("border-t border-border pt-6", sel.make && "pt-4")}>
        <Button
          type="button"
          variant="outline"
          className="h-12 border-2 border-ink/15 bg-white px-5 text-base font-semibold text-ink"
          onClick={() => setUnlisted(true)}
        >
          {t("notListed")}
        </Button>
      </div>
    </div>
  );
}
