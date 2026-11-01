"use client";

import { useState } from "react";

import { cn } from "@im/ui/cn";
import { CatalogueView } from "@/components/vehicles/catalogue-view";
import { UnlistedView } from "@/components/vehicles/unlisted-view";

const TABS = [
  { key: "catalogue", label: "Catalogue" },
  { key: "unlisted", label: "Unlisted cars" },
] as const;

export function VehiclesView() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("catalogue");
  return (
    <div className="flex flex-col gap-4">
      <div role="tablist" aria-label="Vehicles" className="flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            type="button"
            id={`tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`panel-${t.key}`}
            onClick={() => setTab(t.key)}
            className={cn(
              "min-h-11 rounded-full border-2 px-5 font-bold outline-none focus-visible:ring-3 focus-visible:ring-ring",
              tab === t.key ? "border-ink bg-ink text-white" : "border-border bg-white text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "catalogue" ? <CatalogueView /> : <UnlistedView />}
      </div>
    </div>
  );
}
