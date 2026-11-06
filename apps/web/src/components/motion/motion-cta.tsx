"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { loadMotion, prefersReducedMotion } from "./load";

/** A call-to-action button that lifts slightly on hover and presses in on tap (Framer Motion's hover() and press()).
 * The library is loaded the first time a pointer comes near the button; nothing moves with reduced motion. The
 * wrapper stretches with its button in column layouts. */
export function MotionCta({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let cancelled = false;
    const stops: (() => void)[] = [];
    const attach = () => {
      loadMotion().then(
        ({ animate, hover, press }) => {
          if (cancelled) return;
          const spring = { type: "spring", stiffness: 400, damping: 25 } as const;
          const moving = () => !prefersReducedMotion();
          stops.push(
            hover(el, () => {
              if (moving()) animate(el, { y: -2, scale: 1.02 }, spring);
              return () => void animate(el, { y: 0, scale: 1 }, spring);
            }),
            press(el, () => {
              if (moving()) animate(el, { scale: 0.98 }, spring);
              return () => void animate(el, { scale: 1 }, spring);
            }),
          );
          if (el.matches(":hover") && moving()) animate(el, { y: -2, scale: 1.02 }, spring); // already over it
        },
        () => undefined,
      );
    };
    el.addEventListener("pointerenter", attach, { once: true });
    el.addEventListener("pointerdown", attach, { once: true });
    return () => {
      cancelled = true;
      el.removeEventListener("pointerenter", attach);
      el.removeEventListener("pointerdown", attach);
      stops.forEach((s) => s());
    };
  }, []);
  return (
    <div ref={ref} className={className ?? "flex *:flex-1"}>
      {children}
    </div>
  );
}
