// Copies three.js's Draco decoder into public/draco/ (run before `next dev` and `next build`), so the 3D car's
// Draco-compressed GLB is decoded from our own origin: no gstatic or other CDN (Content-Security-Policy:
// packages/ui/src/security-headers.ts). The files follow the installed `three` version; public/draco/ is not committed.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const from = path.dirname(createRequire(import.meta.url).resolve("three/examples/jsm/libs/draco/gltf/draco_decoder.js"));
const to = path.join(here, "../public/draco");
mkdirSync(to, { recursive: true });
for (const file of ["draco_decoder.wasm", "draco_wasm_wrapper.js"]) {
  copyFileSync(path.join(from, file), path.join(to, file));
}
