import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";

export function ErrorMessage({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-2xl border border-ink/15 bg-white p-4 text-ink sm:flex-row sm:items-center"
    >
      <TriangleAlert aria-hidden="true" className="size-5 shrink-0 text-orange-text" />
      <p className="flex-1 text-base">{message}</p>
      {onRetry && (
        <Button type="button" variant="outline" className="h-11 px-5 text-base font-semibold" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
