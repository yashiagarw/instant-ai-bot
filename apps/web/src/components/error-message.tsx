"use client";

import { TriangleAlert } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";

export function ErrorMessage({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const t = useTranslations("common");
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-2xl border border-ink/15 bg-white p-4 text-ink sm:flex-row sm:items-center"
    >
      <TriangleAlert aria-hidden="true" className="size-5 shrink-0 text-orange-text" />
      <p className="flex-1 text-base">{message}</p>
      {onRetry && (
        <Button type="button" variant="outline" className="h-11 px-5 text-base font-semibold" onClick={onRetry}>
          {t("tryAgain")}
        </Button>
      )}
    </div>
  );
}
