"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { cn } from "@im/ui/cn";
import { ChangesTab } from "@/components/knowledge/changes-tab";
import { DraftProvider, useDraft } from "@/components/knowledge/draft";
import { FaultsTab } from "@/components/knowledge/faults-tab";
import { QuestionsTab } from "@/components/knowledge/questions-tab";
import { SafetyTab } from "@/components/knowledge/safety-tab";
import { SignoffTab } from "@/components/knowledge/signoff-tab";
import { TaxonomyTab } from "@/components/knowledge/taxonomy-tab";

const TABS = [
  { key: "faults", label: "Faults" },
  { key: "questions", label: "Questions" },
  { key: "taxonomy", label: "Tiles & categories" },
  { key: "safety", label: "Safety rules" },
  { key: "signoff", label: "Sign-off" },
  { key: "changes", label: "Changes in this draft" },
] as const;

/** The Knowledge editors: a draft bar, then one tab per area (the tab is in the address: ?tab=). */
export function KnowledgeView() {
  return (
    <DraftProvider>
      <Tabs />
    </DraftProvider>
  );
}

function Tabs() {
  const { draft } = useDraft();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = TABS.find((t) => t.key === params.get("tab"))?.key ?? "faults";

  function choose(key: string) {
    const q = new URLSearchParams(params.toString());
    q.set("tab", key);
    router.replace(`${pathname}?${q.toString()}`, { scroll: false });
  }

  if (!draft || draft.building) return null;
  return (
    <div className="flex flex-col gap-4">
      <div role="tablist" aria-label="Knowledge" className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            type="button"
            id={`tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`panel-${t.key}`}
            onClick={() => choose(t.key)}
            className={cn(
              "min-h-11 rounded-full border-2 px-4 font-bold outline-none focus-visible:ring-3 focus-visible:ring-ring",
              tab === t.key ? "border-ink bg-ink text-white" : "border-border bg-white text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="flex flex-col gap-4">
        {tab === "faults" && <FaultsTab />}
        {tab === "questions" && <QuestionsTab />}
        {tab === "taxonomy" && <TaxonomyTab />}
        {tab === "safety" && <SafetyTab />}
        {tab === "signoff" && <SignoffTab />}
        {tab === "changes" && <ChangesTab />}
      </div>
    </div>
  );
}
