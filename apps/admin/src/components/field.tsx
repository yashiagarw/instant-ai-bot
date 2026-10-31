import { useId, type InputHTMLAttributes } from "react";

import { cn } from "@im/ui/cn";

/** A labelled input with an optional hint and error (announced with the input). */
export function Field({
  label,
  hint,
  error,
  className,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }) {
  const id = useId();
  const described = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="font-semibold text-ink">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="text-sm text-ink/75">
          {hint}
        </p>
      )}
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={described}
        className="h-12 rounded-xl border border-input bg-white px-4 text-base text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring aria-invalid:border-orange-text"
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
