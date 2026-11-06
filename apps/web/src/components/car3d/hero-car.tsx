"use client";

import dynamic from "next/dynamic";
import { useCallback, useRef, useState, type ReactNode } from "react";

import { hasWebGL, useAfterInteractive, useCan3D, useOnScreen } from "@/lib/three-d";
import { cn } from "@/lib/utils";

const CarScene = dynamic(() => import("./car-scene"), { ssr: false, loading: () => null });

/** The landing hero's car: the static picture (children, server-rendered) until the 3D car has loaded after the page
 * is interactive; the picture stays when 3D is skipped (lib/three-d.ts). The canvas is decorative: the picture's
 * alt text describes the hero for screen readers either way. */
export function HeroCar({ children }: { children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const can3D = useCan3D();
  const start = useAfterInteractive(can3D);
  const onScreen = useOnScreen(box, { margin: "0px" });
  const [ready, setReady] = useState(false);
  const onReady = useCallback(() => setReady(true), []);
  const show = can3D && start && hasWebGL();
  return (
    <div ref={box} className="relative aspect-[640/420] w-full" data-testid="hero-car" data-3d={show ? (ready ? "ready" : "loading") : "off"}>
      <div className={cn("transition-opacity duration-700", ready && "opacity-0")}>{children}</div>
      {show && (
        <div className={cn("absolute inset-0 opacity-0 transition-opacity duration-700", ready && "opacity-100")}>
          <CarScene mode="hero" spin paused={!onScreen} onReady={onReady} />
        </div>
      )}
    </div>
  );
}
