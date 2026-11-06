"use client";

import { useEffect, useRef, type ComponentProps } from "react";

import { loadMotion, prefersReducedMotion } from "./load";

/** A section that slides in briefly when it appears (each new question: give it a new `key`; `enter={false}` for the
 * first one, which simply shows). Framer Motion's animate(); nothing moves with reduced motion. Content is visible
 * from the first paint, so focus and screen readers never wait for the animation. */
export function EnterSection({ enter = true, ...props }: ComponentProps<"section"> & { enter?: boolean }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !enter || prefersReducedMotion()) return;
    let stop: (() => void) | null = null;
    let cancelled = false;
    loadMotion().then(
      ({ animate }) => {
        if (cancelled || !el.isConnected) return;
        const c = animate(el, { opacity: [0, 1], y: [12, 0] }, { duration: 0.2, ease: "easeOut" });
        stop = () => c.stop();
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
      stop?.();
    };
  }, [enter]);
  return <section ref={ref} {...props} />;
}
