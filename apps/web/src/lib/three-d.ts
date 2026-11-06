"use client";

import { useEffect, useState, useSyncExternalStore, type RefObject } from "react";

// When the 3D car may load (Phase 5.5). The static picture stays, and nothing of three.js is downloaded, when:
//   - the person asked for less motion (prefers-reduced-motion),
//   - the device has little memory (navigator.deviceMemory under 4 GB, where the browser tells us),
//   - the connection is slow or Save-Data is on (navigator.connection: slow-2g, 2g, 3g),
//   - the browser has no WebGL or WebAssembly (the Draco decoder needs it).

export type Skip3DReason = "reduced_motion" | "low_memory" | "slow_connection" | "save_data" | "no_webgl" | null;

interface NetInfo {
  effectiveType?: string;
  saveData?: boolean;
}

const SLOW = new Set(["slow-2g", "2g", "3g"]);
export const MIN_MEMORY_GB = 4;

let webgl: boolean | null = null;
/** WebGL and WebAssembly available. Creating a test context is not free, so this runs only when 3D is about to
 * start (never while a page renders), once, and the test context is released straight away. */
export function hasWebGL(): boolean {
  if (webgl === null) {
    try {
      const c = document.createElement("canvas");
      const gl = (c.getContext("webgl2") ?? c.getContext("webgl")) as WebGLRenderingContext | null;
      webgl = typeof WebAssembly === "object" && !!gl;
      gl?.getExtension?.("WEBGL_lose_context")?.loseContext();
    } catch {
      webgl = false;
    }
  }
  return webgl;
}

/** Why 3D is skipped on this device (null: show it). Browser only. `webgl: false` leaves out the WebGL test (the
 * cheap checks, for rendering). */
export function skip3DReason({ webgl: checkGl = true } = {}): Skip3DReason {
  if (typeof window === "undefined") return "no_webgl";
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? true) return "reduced_motion";
  const nav = navigator as Navigator & { deviceMemory?: number; connection?: NetInfo };
  if (typeof nav.deviceMemory === "number" && nav.deviceMemory < MIN_MEMORY_GB) return "low_memory";
  if (nav.connection?.saveData) return "save_data";
  if (nav.connection?.effectiveType && SLOW.has(nav.connection.effectiveType)) return "slow_connection";
  if (checkGl && !hasWebGL()) return "no_webgl";
  return null;
}

function subscribeMotion(cb: () => void) {
  const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  mq?.addEventListener?.("change", cb);
  return () => mq?.removeEventListener?.("change", cb);
}

/** True when 3D may be shown (the cheap checks; WebGL is tested with hasWebGL() just before starting); false on the
 * server, the first paint and when skipped. Turns off if the person switches on reduced motion while the page is open. */
export function useCan3D(): boolean {
  return useSyncExternalStore(subscribeMotion, () => skip3DReason({ webgl: false }) === null, () => false);
}

const INTERACTIONS = ["pointermove", "pointerdown", "keydown", "scroll", "touchstart"] as const;

/** After the page is interactive: once the page has loaded and the person starts using it (moves the mouse, taps,
 * scrolls or presses a key), the static picture is swapped for the 3D car (the "facade" pattern). The 3D download and
 * its set-up (about 250 KB of three.js and a WebGL start) then never compete with the page's own start-up, and
 * nobody who only glances at the page pays for it. */
export function useAfterInteractive(enabled: boolean): boolean {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!enabled || ready) return;
    let idle = 0;
    let timer = 0;
    const go = () => setReady(true);
    const opts = { once: true, passive: true } as const;
    const start = () => {
      // Let the browser handle the input first, then start in idle time.
      const ric = window.requestIdleCallback;
      if (ric) idle = ric(go, { timeout: 500 });
      else timer = window.setTimeout(go, 50);
    };
    const onLoad = () => INTERACTIONS.forEach((e) => window.addEventListener(e, start, opts));
    if (document.readyState === "complete") onLoad();
    else window.addEventListener("load", onLoad, { once: true });
    return () => {
      window.removeEventListener("load", onLoad);
      INTERACTIONS.forEach((e) => window.removeEventListener(e, start));
      window.clearTimeout(timer);
      if (idle) window.cancelIdleCallback?.(idle);
    };
  }, [enabled, ready]);
  return ready;
}

/** Whether the element is on screen (or near it). Starts false; `once` keeps it true after the first time. */
export function useOnScreen(ref: RefObject<Element | null>, { once = false, margin = "200px" } = {}): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      ([entry]) => {
        setOn(entry.isIntersecting);
        if (entry.isIntersecting && once) io.disconnect();
      },
      { rootMargin: margin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref, once, margin]);
  return on;
}
