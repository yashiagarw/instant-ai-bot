// Framer Motion (the `motion` package) for the customer pages (Phase 5.5), off the critical path: the library is
// imported only when something is about to move (a pointer on a CTA, a price coming into view, the next question),
// after the page has loaded, and never with prefers-reduced-motion. Until then (and with reduced motion) everything
// works and looks the same, just without movement.

type MotionLib = typeof import("motion");
let lib: Promise<MotionLib> | null = null;

export function prefersReducedMotion(): boolean {
  // No matchMedia (tests, very old browsers): no animation.
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** The motion library, loaded once, after load + idle. Rejects (and nothing animates) with reduced motion. */
export function loadMotion(): Promise<MotionLib> {
  if (prefersReducedMotion()) return Promise.reject(new Error("reduced motion"));
  lib ??= new Promise<void>((resolve) => {
    const idle = () => (window.requestIdleCallback ? window.requestIdleCallback(() => resolve(), { timeout: 2000 }) : setTimeout(resolve, 200));
    if (document.readyState === "complete") idle();
    else window.addEventListener("load", idle, { once: true });
  }).then(() => import("motion"));
  return lib;
}
