import { CircleAlert } from "lucide-react";

import { Button } from "@im/ui/button";

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-2xl border border-border bg-white p-4 text-ink">
      <p className="flex items-start gap-2 font-semibold">
        <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-orange-text" />
        {message}
      </p>
      {onRetry && (
        <Button type="button" variant="outline" className="h-11 rounded-full px-5 text-base" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
