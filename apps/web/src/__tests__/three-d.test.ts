import { afterEach, expect, test, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.resetModules();
});

function stub({ reduce = false, memory, net }: { reduce?: boolean; memory?: number; net?: object } = {}) {
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: reduce && q.includes("reduce"), addEventListener() {}, removeEventListener() {} }));
  Object.defineProperty(navigator, "deviceMemory", { value: memory, configurable: true });
  Object.defineProperty(navigator, "connection", { value: net, configurable: true });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as never); // WebGL available
}

async function reason() {
  const { skip3DReason } = await import("@/lib/three-d");
  return skip3DReason();
}

test("3D shows on a capable device", async () => {
  stub({ memory: 8, net: { effectiveType: "4g", saveData: false } });
  expect(await reason()).toBeNull();
});

test("skipped with reduced motion, little memory, a slow connection or Save-Data", async () => {
  stub({ reduce: true, memory: 8 });
  expect(await reason()).toBe("reduced_motion");
  stub({ memory: 2 });
  expect(await reason()).toBe("low_memory");
  stub({ memory: 8, net: { effectiveType: "3g" } });
  expect(await reason()).toBe("slow_connection");
  stub({ memory: 8, net: { effectiveType: "slow-2g" } });
  expect(await reason()).toBe("slow_connection");
  stub({ memory: 8, net: { effectiveType: "4g", saveData: true } });
  expect(await reason()).toBe("save_data");
});

test("skipped without WebGL, and when the browser cannot tell (no matchMedia: treated as reduced motion)", async () => {
  stub({ memory: 8 });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  expect(await reason()).toBe("no_webgl");
  vi.stubGlobal("matchMedia", undefined);
  expect(await reason()).toBe("reduced_motion");
});
