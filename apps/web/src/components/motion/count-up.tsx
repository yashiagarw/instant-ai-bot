"use client";

import { useEffect, useRef, useState } from "react";

import { loadMotion, prefersReducedMotion } from "./load";

const DURATION = 0.8;

export { prefersReducedMotion } from "./load";

/** Numbers that count up from 0 to their value (the estimate on the result page) when they come into view, formatted
 * by `format` (Framer Motion's animate()). Screen readers get the final text only; with reduced motion, or until it
 * is on screen, the final text is shown. */
export function CountUp({ values, format }: { values: number[]; format: (values: number[]) => string }) {
  const key = values.join(",");
  const [shown, setShown] = useState<number[] | null>(null); // null: final values
  const box = useRef<HTMLSpanElement>(null);
  const done = useRef<string | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el || done.current === key || prefersReducedMotion() || typeof IntersectionObserver === "undefined") return;
    const target = key.split(",").map(Number);
    let stop: (() => void) | null = null;
    let cancelled = false;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        done.current = key;
        loadMotion().then(
          ({ animate }) => {
            if (cancelled) return;
            const controls = animate(0, 1, {
              duration: DURATION,
              ease: "easeOut",
              onUpdate: (p) => setShown(target.map((v) => Math.round(v * p))),
              onComplete: () => setShown(null),
            });
            stop = () => controls.stop();
          },
          () => undefined,
        );
      },
      { threshold: 0.6 },
    );
    io.observe(el);
    return () => {
      cancelled = true;
      io.disconnect();
      stop?.();
      setShown(null);
    };
  }, [key]);

  return (
    <span ref={box}>
      {shown ? (
        <>
          <span aria-hidden="true">{format(shown)}</span>
          <span className="sr-only">{format(values)}</span>
        </>
      ) : (
        format(values)
      )}
    </span>
  );
}
