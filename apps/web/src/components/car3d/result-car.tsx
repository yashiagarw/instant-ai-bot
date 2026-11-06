"use client";

import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useCallback, useId, useMemo, useRef, useState } from "react";
import { Car } from "lucide-react";

import { CATEGORY_SYSTEMS, highlightMeshes } from "@/lib/car-parts";
import { hasWebGL, useCan3D, useOnScreen } from "@/lib/three-d";
import { cn } from "@/lib/utils";

const CarScene = dynamic(() => import("./car-scene"), { ssr: false, loading: () => null });

/** "Where it is on the car": the diagnosed category's part highlighted in orange on the generic 3D car (config:
 * lib/car-parts.ts). The 3D loads only when this card comes on screen, and never when 3D is skipped on the device
 * (lib/three-d.ts); the text always names the part, so nothing depends on the picture. Categories with no clear part
 * show the car without a highlight (and no card at all when 3D is skipped). */
export function ResultCar({ category }: { category: string }) {
  const t = useTranslations("result.car3d");
  const tp = useTranslations("carParts");
  const id = useId();
  const box = useRef<HTMLDivElement>(null);
  const can3D = useCan3D();
  const near = useOnScreen(box, { once: true });
  const onScreen = useOnScreen(box, { margin: "0px" });
  const [ready, setReady] = useState(false);
  const onReady = useCallback(() => setReady(true), []);
  const systems = CATEGORY_SYSTEMS[category] ?? null;
  const highlight = useMemo(() => highlightMeshes(category), [category]);

  // WebGL is tested only once the card is near the screen (creating a test context is not free).
  const gl = near ? hasWebGL() : true;
  if (!systems && !(can3D && gl)) return null;
  const show = can3D && gl && near;
  return (
    <section
      aria-labelledby={`${id}-h`}
      className="flex flex-col gap-3 rounded-3xl border border-border bg-white p-5"
      data-testid="result-car"
      data-3d={show ? (ready ? "ready" : "loading") : "off"}
      data-highlight={highlight.join(" ")}
    >
      <h2 id={`${id}-h`} className="flex items-center gap-2 text-xl font-black text-ink">
        <Car aria-hidden="true" className="size-5 text-orange-text" />
        {t("title")}
      </h2>
      <p className="text-ink">
        {systems ? (
          <>
            <span aria-hidden="true" className="mr-2 inline-block size-3 rounded-full bg-brand align-middle" />
            {t("highlighted", { parts: systems.map((s) => tp(s)).join(", ") })}
          </>
        ) : (
          t("noPart")
        )}
      </p>
      {can3D && gl && (
        <div ref={box} className="relative aspect-[4/3] w-full overflow-hidden rounded-2xl bg-warm-white sm:aspect-[16/9]">
          {show && (
            <div className={cn("absolute inset-0 opacity-0 transition-opacity duration-500", ready && "opacity-100")}>
              <CarScene mode="result" highlight={highlight} spin paused={!onScreen} onReady={onReady} />
            </div>
          )}
        </div>
      )}
      {can3D && gl && <p className="text-sm text-ink/75">{t("approximate")}</p>}
    </section>
  );
}
