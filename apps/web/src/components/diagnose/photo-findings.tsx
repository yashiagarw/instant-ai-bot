"use client";

import { Camera, CircleAlert } from "lucide-react";

import { type Finding, type Photo, photosApi, type SafetyAlert } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

export const MECHANIC_LOOKS = "A mechanic will look at your photo.";
export const PHOTOS_MISLEAD = "Photos can be misleading. A mechanic will check this before any repair.";

/** The safety alerts from photo findings (a red warning light, dangerous damage), once per rule. */
export function photoAlerts(photos: Photo[], seen: SafetyAlert[] = []): SafetyAlert[] {
  const ids = new Set(seen.map((a) => a.rule_id));
  const out: SafetyAlert[] = [];
  for (const a of photos.flatMap((p) => p.findings ?? []).flatMap((f) => f.safety)) {
    if (!ids.has(a.rule_id)) {
      ids.add(a.rule_id);
      out.push(a);
    }
  }
  return out;
}

/** The customer's ready photos for a session; a failure just shows none (photos never block a page). */
export function usePhotos(sessionId: string | null): Photo[] {
  const loaded = useLoad(sessionId ? `photos:${sessionId}` : null, (signal) => photosApi.list(sessionId!, signal));
  return loaded.state.status === "ready" ? loaded.state.data : [];
}

/** What one photo may show: "Possible: ..." with the meaning, or why there is nothing (retake / a mechanic looks). */
export function PhotoFindings({ findings }: { findings: Finding[] }) {
  if (!findings.length) return <p className="text-sm text-ink/80">{MECHANIC_LOOKS}</p>;
  const found = findings.filter((f) => f.status === "found");
  if (!found.length) {
    const unclear = findings.find((f) => f.status === "unclear");
    return <p className="text-sm text-ink/80">{unclear ? unclear.message : MECHANIC_LOOKS}</p>;
  }
  return (
    <div className="flex flex-col gap-2" data-testid="photo-findings">
      <ul className="flex flex-col gap-2">
        {found
          .flatMap((f) => f.labels)
          .map((l) => (
            <li key={l.code} className="text-sm text-ink">
              <p className="font-bold">
                Possible: {l.name}
                {l.severity === "red" && (
                  <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-danger px-2 py-0.5 text-xs font-bold text-white">
                    <CircleAlert aria-hidden="true" className="size-3.5" />
                    Red light
                  </span>
                )}
              </p>
              {l.meaning && <p className="text-ink/80">{l.meaning}</p>}
            </li>
          ))}
      </ul>
      <p className="text-xs text-ink/70">{PHOTOS_MISLEAD}</p>
    </div>
  );
}

/** The customer's photos with their findings (results page, mechanic request page). Nothing when there are none. */
export function PhotoGallery({ photos, className }: { photos: Photo[]; className?: string }) {
  if (!photos.length) return null;
  return (
    <section
      aria-labelledby="photos-h"
      className={cn("flex flex-col gap-4 rounded-3xl border border-border bg-white p-5", className)}
      data-testid="photo-gallery"
    >
      <h2 id="photos-h" className="flex items-center gap-2 text-xl font-black text-ink">
        <Camera aria-hidden="true" className="size-5 text-orange-text" />
        Your photos
      </h2>
      <ul className="grid gap-4 sm:grid-cols-2">
        {photos.map((p, i) => (
          <li key={p.id} className="flex flex-col gap-2">
            {p.url ? (
              // eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link from the API
              <img
                src={p.url}
                alt={`Your photo ${i + 1}`}
                className="aspect-[4/3] w-full rounded-2xl bg-warm-white object-cover"
              />
            ) : (
              <div className="flex aspect-[4/3] items-center justify-center rounded-2xl bg-warm-white text-sm text-ink/70">
                Photo {i + 1}
              </div>
            )}
            <PhotoFindings findings={p.findings ?? []} />
          </li>
        ))}
      </ul>
    </section>
  );
}
