// Writes public/sw.js (Phase 5.5), run by `pnpm build` and `pnpm dev` before Next starts:
//   node scripts/service-worker.mjs          production: src/service-worker/sw.template.js with a build id unique to
//                                            this build (BUILD_ID from the environment, else time + random), so each
//                                            deploy is a new worker whose caches replace the previous build's
//   node scripts/service-worker.mjs --dev    development: src/service-worker/sw.dev-reset.js, which removes any worker
//                                            and cache a browser kept from a production build
// public/sw.js is generated, not committed.
import { randomBytes } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(here, "../src/service-worker");
export const OUT = path.join(here, "../public/sw.js");

export function newBuildId() {
  return process.env.BUILD_ID || `${Date.now().toString(36)}-${randomBytes(4).toString("hex")}`;
}

/** The /sw.js source for one build (or for development). */
export function serviceWorkerSource({ build, dev = false }) {
  if (dev) return readFileSync(path.join(SRC, "sw.dev-reset.js"), "utf8");
  if (!/^[\w.-]+$/.test(build)) throw new Error(`invalid build id: ${build}`);
  const template = readFileSync(path.join(SRC, "sw.template.js"), "utf8");
  if (!template.includes('"__BUILD_ID__"')) throw new Error("sw.template.js has no __BUILD_ID__");
  return template.replace('"__BUILD_ID__"', JSON.stringify(build));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dev = process.argv.includes("--dev");
  const build = dev ? "dev" : newBuildId();
  writeFileSync(OUT, serviceWorkerSource({ build, dev }));
  console.log(`public/sw.js: ${dev ? "development (no service worker)" : `build ${build}`}`);
}
