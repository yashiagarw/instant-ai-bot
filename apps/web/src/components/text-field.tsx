"use client";

import { useId } from "react";

/** A labelled text input (56px tall pill) with an error message under it. */
export function TextField({
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
