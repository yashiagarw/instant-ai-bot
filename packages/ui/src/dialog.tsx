"use client";

import type { ReactNode } from "react";
import { Dialog as D } from "radix-ui";
import { X } from "lucide-react";

import { cn } from "./cn";

/** A modal dialog (Radix: focus trapped, Escape and the close button close it, focus returns to the opener). */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-ink/40" />
        <D.Content
          className={cn(
            "fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-3xl bg-white p-6 text-ink shadow-xl outline-none",
            className,
          )}
          {...(description ? {} : { "aria-describedby": undefined })}
        >
          <div className="flex items-start justify-between gap-3">
            <D.Title className="text-xl font-black">{title}</D.Title>
            <D.Close
              aria-label="Close"
              className="-mt-2 -mr-2 flex size-11 shrink-0 items-center justify-center rounded-full outline-none hover:bg-warm-white focus-visible:ring-3 focus-visible:ring-ring"
            >
              <X aria-hidden="true" className="size-5" />
            </D.Close>
          </div>
          {description && <D.Description className="text-ink/80">{description}</D.Description>}
          {children}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
