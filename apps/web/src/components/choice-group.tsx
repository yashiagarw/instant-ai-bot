"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";

export interface Choice<T extends string | number> {
  value: T;
  label: string;
  hint?: string;
}

/** A question answered with large pill toggles. Native radio buttons: Tab moves into the group, arrow keys move
 * between choices, and the focus ring is always visible. */
export function ChoiceGroup<T extends string | number>({
  legend,
  choices,
  value,
  onChange,
  columns = "grid-cols-2 sm:grid-cols-3",
  error,
}: {
  legend: string;
  choices: Choice<T>[];
  value: T | undefined;
  onChange: (value: T) => void;
  columns?: string;
  error?: string;
}) {
  const name = useId();
  return (
    <fieldset className="flex flex-col gap-3" aria-describedby={error ? `${name}-error` : undefined}>
      <legend className="mb-3 text-lg font-bold text-ink">{legend}</legend>
      <div className={cn("grid gap-2.5", columns)}>
        {choices.map((c) => {
          const id = `${name}-${c.value}`;
          return (
            <div key={c.value}>
              <input
                id={id}
                type="radio"
                name={name}
                className="peer sr-only"
                checked={value === c.value}
                onChange={() => onChange(c.value)}
              />
              <label
                htmlFor={id}
                className={cn(
                  "flex min-h-12 w-full cursor-pointer flex-col items-center justify-center rounded-full border-2 border-ink/15 bg-white px-4 py-2 text-center text-base font-semibold text-ink transition-colors",
                  // Important: route CSS chunks can repeat base utilities later in the same layer and would win otherwise.
                  "hover:border-cta/60 peer-checked:border-orange-text! peer-checked:bg-[#ffe6d3]! peer-checked:shadow-[inset_0_0_0_1px_var(--color-orange-text)]",
                  "peer-focus-visible:ring-3 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2",
                )}
              >
                {c.label}
                {c.hint && <span className="text-xs font-normal text-ink/70">{c.hint}</span>}
              </label>
            </div>
          );
        })}
      </div>
      {error && (
        <p id={`${name}-error`} className="text-sm font-semibold text-orange-text">
          {error}
        </p>
      )}
    </fieldset>
  );
}
