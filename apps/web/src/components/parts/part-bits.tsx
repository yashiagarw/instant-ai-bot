import Link from "next/link";
import { BadgeCheck, CircleHelp, Package, ShieldCheck } from "lucide-react";

import { mediaUrl, type BrandKind, type FitStatus, type Part, type PartPrice } from "@/lib/api";
import { rupeeRange } from "@/lib/format";
import { cn } from "@/lib/utils";

export const FIT: Record<FitStatus, { label: string; className: string; Icon: typeof BadgeCheck }> = {
  listed: { label: "Fits your car", className: "border-success/30 bg-success-bg text-success", Icon: BadgeCheck },
  confirm_fit: {
    label: "Fits your model · confirm with your VIN",
    className: "border-success/30 bg-success-bg text-success",
    Icon: ShieldCheck,
  },
  not_verified: {
    label: "Fit not verified for your car",
    className: "border-amber-text/30 bg-amber-bg text-amber-text",
    Icon: CircleHelp,
  },
};

const BRAND: Record<BrandKind, string> = {
  oem: "Genuine (OEM)",
  oes: "OE supplier (OES)",
  aftermarket: "Aftermarket",
  unspecified: "Brand not stated",
};

/** "Genuine (OEM)", "OE supplier (OES)", "Aftermarket", or "Any good brand" for a part described by type only. */
export function brandType(part: Pick<Part, "brand" | "generic">): string {
  if (part.brand) return BRAND[part.brand.kind];
  return part.generic ? "Any good brand" : "Brand not stated";
}

export function FitBadge({ status }: { status: FitStatus }) {
  const f = FIT[status];
  return (
    <span
      data-testid="fit-badge"
      className={cn("inline-flex items-center gap-1.5 self-start rounded-full border px-2.5 py-1 text-sm font-bold", f.className)}
    >
      <f.Icon aria-hidden="true" className="size-4 shrink-0" />
      {f.label}
    </span>
  );
}

export function BrandBadge({ part }: { part: Pick<Part, "brand" | "generic"> }) {
  return (
    <span className="inline-flex items-center rounded-full bg-ink/8 px-2.5 py-1 text-sm font-semibold text-ink">
      {brandType(part)}
    </span>
  );
}

/** The lowest to highest price among the given rows, or null. */
export function priceSpan(prices: PartPrice[]): { low: number; high: number } | null {
  if (prices.length === 0) return null;
  return {
    low: Math.min(...prices.map((p) => p.price_inr)),
    high: Math.max(...prices.map((p) => p.price_max_inr ?? p.price_inr)),
  };
}

export function PriceText({ prices, className }: { prices: PartPrice[]; className?: string }) {
  const span = priceSpan(prices);
  return (
    <span className={cn("font-black text-ink tabular-nums", className)} data-testid="part-price">
      {span ? rupeeRange(span.low, span.high) : "Price on inspection"}
    </span>
  );
}

export function PartImage({ part, className }: { part: Part; className?: string }) {
  const image = part.images[0];
  if (!image) {
    return (
      <div
        aria-hidden="true"
        className={cn("flex aspect-[4/3] w-full items-center justify-center rounded-2xl bg-warm-white", className)}
      >
        <Package className="size-10 text-orange-text/60" />
      </div>
    );
  }
  return (
    <div className={cn("relative overflow-hidden rounded-2xl bg-warm-white", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- pictures come from the API's /media */}
      <img
        src={mediaUrl(image.file)}
        alt={image.caption ? `Illustration: ${image.caption}` : `Illustration of ${part.name}`}
        loading="lazy"
        className="aspect-[4/3] w-full object-contain"
      />
      <span className="absolute top-2 left-2 rounded-full bg-ink/80 px-2 py-0.5 text-xs font-bold text-white">
        Illustration
      </span>
    </div>
  );
}

export function partHref(id: number, variantId: number | null | undefined): string {
  return variantId ? `/parts/${id}?variant_id=${variantId}` : `/parts/${id}`;
}

/** One part: picture, name, brand type, price for the car's segment and whether it fits the car. */
export function PartCard({
  part,
  variantId,
  compare,
}: {
  part: Part;
  variantId: number | null | undefined;
  compare?: { checked: boolean; disabled: boolean; onChange: (checked: boolean) => void };
}) {
  return (
    <article
      aria-label={part.name}
      data-testid="part-card"
      className="flex w-full flex-col gap-3 rounded-3xl border border-border bg-white p-4"
    >
      <PartImage part={part} />
      <div className="flex flex-col gap-2">
        <h3 className="text-lg leading-snug font-black text-ink">
          <Link
            href={partHref(part.id, variantId)}
            className="inline-flex min-h-11 items-center rounded outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
          >
            {part.name}
          </Link>
        </h3>
        <div className="flex flex-wrap gap-2">
          <BrandBadge part={part} />
          {part.in_total === false && (
            <span className="inline-flex items-center rounded-full bg-ink/8 px-2.5 py-1 text-sm font-semibold text-ink">
              Only if needed
            </span>
          )}
        </div>
        <FitBadge status={part.fit.status} />
        <p className="text-xl">
          <PriceText prices={part.prices} />
        </p>
      </div>
      {compare && (
        <label className="mt-auto inline-flex min-h-11 cursor-pointer items-center gap-2 font-semibold text-ink">
          <input
            type="checkbox"
            checked={compare.checked}
            disabled={compare.disabled && !compare.checked}
            onChange={(e) => compare.onChange(e.target.checked)}
            className="size-5 accent-cta"
          />
          Compare
        </label>
      )}
    </article>
  );
}
