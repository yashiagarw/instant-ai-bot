"use client";

import { useId, useState } from "react";
import { MapPin } from "lucide-react";

import type { Area, ZoneCode } from "@/lib/api";
import { cn } from "@/lib/utils";

export const ZONES: { code: ZoneCode; label: string }[] = [
  { code: "delhi", label: "Delhi" },
  { code: "noida", label: "Noida" },
  { code: "gurugram", label: "Gurugram" },
  { code: "ghaziabad", label: "Ghaziabad" },
  { code: "faridabad", label: "Faridabad" },
];

export const METRO_LABEL = "Delhi NCR metro estimate";

/** "Your area": a Delhi NCR zone or a pincode; labour prices follow it. Without one, the metro estimate is used. */
export function AreaPicker({
  area,
  onChange,
  note,
}: {
  area: Area;
  onChange: (area: Area) => void;
  note?: string;
}) {
  const name = useId();
  const [pin, setPin] = useState(area && "pincode" in area ? area.pincode : "");
  const [error, setError] = useState("");
  const zone = area && "zone" in area ? area.zone : null;

  function applyPincode() {
    const p = pin.replace(/\s/g, "");
    if (!/^\d{6}$/.test(p)) {
      setError("Enter a 6-digit pincode");
      return;
    }
    setError("");
    onChange({ pincode: p });
  }

  return (
    <fieldset className="flex flex-col gap-3 rounded-2xl bg-warm-white p-4" data-testid="area-picker">
      <legend className="sr-only">Your area</legend>
      <p aria-hidden="true" className="flex items-center gap-2 font-bold text-ink">
        <MapPin className="size-5 text-orange-text" />
        Your area
      </p>
      <div className="flex flex-wrap gap-2">
        {ZONES.map((z) => {
          const id = `${name}-${z.code}`;
          return (
            <div key={z.code}>
              <input
                id={id}
                type="radio"
                name={name}
                className="peer sr-only"
                checked={zone === z.code}
                onChange={() => {
                  setError("");
                  onChange({ zone: z.code });
                }}
              />
              <label
                htmlFor={id}
                className={cn(
                  "inline-flex min-h-11 cursor-pointer items-center rounded-full border-2 border-ink/15 bg-white px-4 font-semibold text-ink",
                  "hover:border-cta/60 peer-checked:border-orange-text! peer-checked:bg-[#ffe6d3]!",
                  "peer-focus-visible:ring-3 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2",
                )}
              >
                {z.label}
              </label>
            </div>
          );
        })}
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${name}-pin`} className="text-sm font-semibold text-ink/80">
          Or your pincode
        </label>
        <div className="flex gap-2">
          <input
            id={`${name}-pin`}
            inputMode="numeric"
            autoComplete="postal-code"
            maxLength={6}
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), applyPincode())}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? `${name}-pin-error` : undefined}
            className="h-11 w-36 rounded-full border-2 border-ink/15 bg-white px-4 text-base text-ink tabular-nums outline-none focus-visible:border-cta focus-visible:ring-3 focus-visible:ring-ring/40 aria-invalid:border-orange-text"
          />
          <button
            type="button"
            onClick={applyPincode}
            className="h-11 rounded-full border-2 border-ink/15 bg-white px-4 font-bold text-ink outline-none hover:border-cta/60 focus-visible:ring-3 focus-visible:ring-ring"
          >
            Use pincode
          </button>
        </div>
        {error && (
          <p id={`${name}-pin-error`} className="text-sm font-semibold text-orange-text">
            {error}
          </p>
        )}
      </div>
      <p className="text-sm text-ink/80" data-testid="area-note" aria-live="polite">
        {note || METRO_LABEL}
      </p>
    </fieldset>
  );
}
