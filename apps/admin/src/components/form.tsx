"use client";

// Small form building blocks for React Hook Form: a label, the control and its error, announced together.

import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import type { FieldError } from "react-hook-form";

import { cn } from "@im/ui/cn";

const CONTROL =
  "w-full rounded-xl border border-input bg-white px-4 text-base text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring aria-invalid:border-orange-text";

type Common = { label: string; error?: FieldError | { message?: string }; hint?: ReactNode; className?: string };

function Wrap({ id, label, error, hint, className, children }: Common & { id: string; children: ReactNode }) {
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
      {children}
      {error?.message && (
        <p id={`${id}-error`} className="text-sm font-semibold text-orange-text">
          {error.message}
        </p>
      )}
    </div>
  );
}

function describedBy(id: string, hint: unknown, error: unknown) {
  return [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ") || undefined;
}

export const TextInput = forwardRef<HTMLInputElement, Common & InputHTMLAttributes<HTMLInputElement>>(function TextInput(
  { label, error, hint, className, ...input },
  ref,
) {
  const id = useId();
  return (
    <Wrap id={id} label={label} error={error} hint={hint} className={className}>
      <input
        id={id}
        ref={ref}
        lang="mul"
        aria-invalid={error?.message ? true : undefined}
        aria-describedby={describedBy(id, hint, error?.message)}
        className={cn(CONTROL, "h-12")}
        {...input}
      />
    </Wrap>
  );
});

export const TextArea = forwardRef<HTMLTextAreaElement, Common & TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea(
  { label, error, hint, className, rows = 3, ...input },
  ref,
) {
  const id = useId();
  return (
    <Wrap id={id} label={label} error={error} hint={hint} className={className}>
      <textarea
        id={id}
        ref={ref}
        rows={rows}
        aria-invalid={error?.message ? true : undefined}
        aria-describedby={describedBy(id, hint, error?.message)}
        className={cn(CONTROL, "py-3")}
        {...input}
      />
    </Wrap>
  );
});

export const Select = forwardRef<HTMLSelectElement, Common & SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }>(
  function Select({ label, error, hint, className, options, ...select }, ref) {
    const id = useId();
    return (
      <Wrap id={id} label={label} error={error} hint={hint} className={className}>
        <select
          id={id}
          ref={ref}
          aria-invalid={error?.message ? true : undefined}
          aria-describedby={describedBy(id, hint, error?.message)}
          className={cn(CONTROL, "h-12")}
          {...select}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </Wrap>
    );
  },
);

export const Checkbox = forwardRef<HTMLInputElement, { label: ReactNode; className?: string } & InputHTMLAttributes<HTMLInputElement>>(
  function Checkbox({ label, className, ...input }, ref) {
    return (
      <label className={cn("flex min-h-11 items-center gap-3 font-semibold text-ink", className)}>
        <input type="checkbox" ref={ref} className="size-5 shrink-0 accent-cta" {...input} />
        {label}
      </label>
    );
  },
);

/** The outcome of the last save, announced to screen readers. */
export function SaveStatus({ status }: { status: { kind: "idle" } | { kind: "saved"; text: string } | { kind: "error"; text: string } }) {
  if (status.kind === "idle") return <p aria-live="polite" className="sr-only" />;
  return (
    <p aria-live="polite" role={status.kind === "error" ? "alert" : undefined} className={cn("font-semibold", status.kind === "error" ? "text-orange-text" : "text-success")}>
      {status.text}
    </p>
  );
}

export type Status = Parameters<typeof SaveStatus>[0]["status"];

export function useStatus() {
  return useState<Status>({ kind: "idle" });
}

/** "Edited in this draft" marker. */
export function EditedBadge({ show, label = "Edited in this draft" }: { show: unknown; label?: string }) {
  if (!show) return null;
  return <span className="inline-flex rounded-full bg-amber-bg px-2.5 py-0.5 text-xs font-bold text-amber-text">{label}</span>;
}

/** Number inputs: an empty box means null. */
export const numberOrNull = (v: unknown) => (v === "" || v === null || v === undefined || Number.isNaN(v) ? null : Number(v));
