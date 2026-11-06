// Builds the generic low-poly car for the 3D views (Phase 5.5): public/3d/car.glb, Draco-compressed.
//
//   pnpm build:car           (from apps/web; Node 22.18+ runs this TypeScript file directly)
//
// The car is made here from simple shapes (an extruded side profile, boxes, cylinders): it is not a copy of any
// real car. Every part is its own node, named as in src/lib/car-parts.ts, so the result page can highlight a system
// and a designer's GLB with the same names can replace this file later. Units are metres; +x is the front,
// +y is up, the driver sits on the right (India).
//
// The output is committed, so a normal build does not need to run this. Re-run it after changing the shapes or the
// part names, then run `pnpm test` (src/__tests__/car-parts.test.ts checks the names and the size limit).

import { mkdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Document, NodeIO } from "@gltf-transform/core";
import { KHRDracoMeshCompression } from "@gltf-transform/extensions";
import { dedup, draco, prune, weld } from "@gltf-transform/functions";
import draco3d from "draco3dgltf";
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

import { MESHES, type MeshName } from "../src/lib/car-parts.ts";

const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "../public/3d/car.glb");
const MAX_BYTES = 1.5 * 1024 * 1024;

// ---------------------------------------------------------------- materials (PBR base colours)

const MATERIALS = {
  paint: { color: "#ECE7E1", metal: 0.2, rough: 0.45 },
  glass: { color: "#26313D", metal: 0.1, rough: 0.15 },
  rubber: { color: "#1E1E1E", metal: 0, rough: 0.9 },
  rim: { color: "#B9BEC4", metal: 0.8, rough: 0.35 },
  metal: { color: "#8C9399", metal: 0.7, rough: 0.45 },
  part: { color: "#6E747B", metal: 0.3, rough: 0.6 },
  plastic: { color: "#34373B", metal: 0, rough: 0.7 },
  head_light: { color: "#FFF4D6", metal: 0, rough: 0.2 },
  tail_light: { color: "#B71C1C", metal: 0, rough: 0.3 },
  plate: { color: "#F5F5F5", metal: 0, rough: 0.6 },
  screen: { color: "#10161D", metal: 0.2, rough: 0.2 },
} as const;
type MaterialName = keyof typeof MATERIALS;

// ---------------------------------------------------------------- shape helpers

type V3 = [number, number, number];

function place(g: THREE.BufferGeometry, at: V3, rot: V3 = [0, 0, 0]): THREE.BufferGeometry {
  g.applyMatrix4(
    new THREE.Matrix4().compose(
      new THREE.Vector3(...at),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(...rot)),
      new THREE.Vector3(1, 1, 1),
    ),
  );
  return g;
}
const box = (size: V3, at: V3, rot?: V3) => place(new THREE.BoxGeometry(...size), at, rot);
/** A cylinder along the z axis (wheels, discs) unless rotated. */
const cylZ = (r: number, len: number, at: V3, seg = 16) =>
  place(new THREE.CylinderGeometry(r, r, len, seg), at, [Math.PI / 2, 0, 0]);
const cylX = (r: number, len: number, at: V3, seg = 12) =>
  place(new THREE.CylinderGeometry(r, r, len, seg), at, [0, 0, Math.PI / 2]);
const cylY = (r: number, len: number, at: V3, seg = 12) => place(new THREE.CylinderGeometry(r, r, len, seg), at);

/** A side profile (x, y points) extruded across the car, centred on z. */
function extrudeProfile(points: [number, number][], width: number, bevel = 0.04): THREE.BufferGeometry {
  const shape = new THREE.Shape(points.map(([x, y]) => new THREE.Vector2(x, y)));
  const g = new THREE.ExtrudeGeometry(shape, {
    depth: width - 2 * bevel,
    bevelEnabled: bevel > 0,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments: 1,
    curveSegments: 6,
  });
  return place(g, [0, 0, -(width - 2 * bevel) / 2]);
}

/** A slab between two points of the side profile (windscreen, bonnet), `width` across the car. */
// `lift` clears the body's 4 cm bevel (extrudeProfile), so the panel sits on the outside.
function slab(a: [number, number], b: [number, number], width: number, thick = 0.02, lift = 0.052): THREE.BufferGeometry {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  const angle = Math.atan2(dy, dx);
  // Lift along the surface normal that points up and out of the body (whichever way the two points are given).
  const up = Math.cos(angle) >= 0 ? 1 : -1;
  const nx = -Math.sin(angle) * lift * up;
  const ny = Math.cos(angle) * lift * up;
  return box([len, thick, width], [(a[0] + b[0]) / 2 + nx, (a[1] + b[1]) / 2 + ny, 0], [0, 0, angle]);
}

// ---------------------------------------------------------------- the car

const WHEEL_R = 0.31;
const AXLE_X = 1.28;
const TRACK_Z = 0.72;
const HALF_W = 0.8;

// Side profile of the body: rear bottom -> front, then over the roof back to the rear. Wheel arches are cut out.
const ARCH = 0.39;
const profile: [number, number][] = [[-2.0, 0.3]];
for (const cx of [-AXLE_X, AXLE_X]) {
  profile.push([cx - ARCH, 0.3]);
  for (let i = 0; i <= 8; i++) {
    const t = Math.PI - (i / 8) * Math.PI;
    profile.push([cx + Math.cos(t) * ARCH, WHEEL_R + Math.sin(t) * ARCH]);
  }
  profile.push([cx + ARCH, 0.3]);
}
profile.push(
  [2.0, 0.3], [2.06, 0.52], [1.98, 0.74], [0.95, 0.86], // front bumper, bonnet
  [0.22, 1.34], [-0.95, 1.36], // windscreen, roof
  [-1.72, 0.98], [-2.02, 0.9], [-2.05, 0.55], // rear glass, boot, rear bumper
);

const parts: Record<MeshName, { geo: THREE.BufferGeometry[]; mat: MaterialName }> = {} as never;
const add = (name: MeshName, mat: MaterialName, ...geo: THREE.BufferGeometry[]) => {
  parts[name] = { geo, mat };
};

// Body and panels
add("body_shell", "paint", extrudeProfile(profile, 2 * HALF_W));
add("bumper_front", "plastic", box([0.12, 0.18, 1.62], [2.03, 0.38, 0]));
add("bumper_rear", "plastic", box([0.12, 0.2, 1.62], [-2.02, 0.42, 0]));
add("bonnet", "paint", slab([1.96, 0.74], [0.97, 0.86], 1.5));
add("boot_lid", "paint", slab([-1.74, 0.98], [-2.0, 0.9], 1.4));
for (const [name, z] of [["door_fl", -1], ["door_fr", 1], ["door_rl", -1], ["door_rr", 1]] as const) {
  const front = name.endsWith("fl") || name.endsWith("fr");
  const zz = z * (HALF_W + 0.006);
  add(name, "paint", box([0.98, 0.46, 0.012], [front ? 0.3 : -0.72, 0.63, zz]));
  const handle = `door_handle_${name.slice(5)}` as MeshName;
  add(handle, "metal", box([0.14, 0.035, 0.02], [front ? 0.0 : -1.0, 0.8, z * (HALF_W + 0.018)]));
}

// Glass
add("windscreen", "glass", slab([0.93, 0.87], [0.24, 1.33], 1.42));
add("rear_glass", "glass", slab([-0.97, 1.35], [-1.7, 0.99], 1.36));
for (const [name, z] of [["side_glass_l", 1], ["side_glass_r", -1]] as const) {
  const win = extrudeProfile([[0.82, 0.9], [0.2, 1.3], [-0.92, 1.31], [-1.55, 0.95], [-1.5, 0.9]], 0.02, 0);
  add(name, "glass", place(win, [0, 0, z * (HALF_W + 0.004)]));
}
add("sunroof", "glass", box([0.62, 0.02, 0.72], [-0.4, 1.41, 0]));
add("wiper_l", "plastic", box([0.02, 0.015, 0.52], [1.0, 0.925, 0.3], [0, 0.25, 0]));
add("wiper_r", "plastic", box([0.02, 0.015, 0.52], [1.0, 0.925, -0.3], [0, 0.25, 0]));
add("mirror_l", "paint", box([0.12, 0.1, 0.16], [0.8, 0.96, HALF_W + 0.08]));
add("mirror_r", "paint", box([0.12, 0.1, 0.16], [0.8, 0.96, -(HALF_W + 0.08)]));
add("irvm", "plastic", box([0.03, 0.06, 0.2], [0.28, 1.25, 0]));

// Wheels, brakes, suspension
for (const [suffix, x, z] of [["fl", 1, 1], ["fr", 1, -1], ["rl", -1, 1], ["rr", -1, -1]] as const) {
  const at: V3 = [x * AXLE_X, WHEEL_R, z * TRACK_Z];
  add(`tyre_${suffix}`, "rubber", cylZ(WHEEL_R, 0.21, at, 20));
  add(`wheel_${suffix}`, "rim", cylZ(0.2, 0.215, at, 20));
  add(`brake_disc_${suffix}`, "metal", cylZ(0.165, 0.03, [at[0], at[1], z * (TRACK_Z - 0.14)], 20));
  add(`brake_caliper_${suffix}`, "tail_light", box([0.1, 0.12, 0.05], [at[0] - 0.12, at[1] + 0.08, z * (TRACK_Z - 0.14)]));
  add(`suspension_${suffix}`, "part", cylY(0.05, 0.42, [at[0], at[1] + 0.3, z * (TRACK_Z - 0.2)]));
}

// Engine bay (transverse engine, gearbox on the left side of the bay)
add("engine", "part", box([0.5, 0.3, 0.52], [1.38, 0.57, 0.12]));
add("spark_plugs", "metal", ...[-0.12, 0.0, 0.12, 0.24].map((z) => cylY(0.025, 0.06, [1.38, 0.75, z])));
add("throttle_body", "metal", cylX(0.05, 0.1, [1.08, 0.66, 0.18]));
add("engine_belt", "rubber", place(new THREE.TorusGeometry(0.13, 0.015, 6, 20), [1.42, 0.58, 0.395]));
add("clutch", "metal", cylZ(0.15, 0.06, [1.38, 0.55, -0.18], 20));
add("gearbox", "part", box([0.36, 0.3, 0.3], [1.38, 0.52, -0.38]));
add("drive_shaft", "metal", cylZ(0.025, 1.3, [AXLE_X, WHEEL_R, 0], 8));
add("radiator", "metal", box([0.05, 0.34, 1.1], [1.86, 0.58, 0]));
add("ac_condenser", "part", box([0.03, 0.3, 1.05], [1.93, 0.56, 0]));
add("ac_compressor", "metal", cylZ(0.07, 0.14, [1.62, 0.46, 0.33]));
add(
  "cooling_hose",
  "rubber",
  new THREE.TubeGeometry(
    new THREE.CatmullRomCurve3([
      new THREE.Vector3(1.84, 0.7, 0.3),
      new THREE.Vector3(1.75, 0.8, 0.25),
      new THREE.Vector3(1.62, 0.78, 0.2),
    ]),
    8, 0.025, 6, false,
  ),
);
add("battery", "plastic", box([0.24, 0.2, 0.17], [1.6, 0.66, 0.6]));
add("starter_motor", "metal", cylX(0.06, 0.2, [1.12, 0.44, -0.22]));
add("fuse_box", "plastic", box([0.16, 0.1, 0.12], [1.62, 0.7, -0.62]));
add(
  "wiring_harness",
  "plastic",
  new THREE.TubeGeometry(
    new THREE.CatmullRomCurve3([
      new THREE.Vector3(1.6, 0.78, 0.6),
      new THREE.Vector3(1.3, 0.85, 0.5),
      new THREE.Vector3(0.95, 0.9, 0.2),
      new THREE.Vector3(0.75, 0.9, -0.2),
    ]),
    16, 0.012, 5, false,
  ),
);
add("horn", "part", cylX(0.05, 0.03, [1.98, 0.5, 0.5]));
add("underbody_shield", "plastic", box([0.9, 0.02, 1.1], [1.4, 0.26, 0]));
add("steering_rack", "metal", cylZ(0.03, 1.0, [1.12, 0.4, 0], 8));

// Lights and plates
add("headlight_l", "head_light", box([0.06, 0.1, 0.32], [2.03, 0.66, 0.56], [0, 0, -0.35]));
add("headlight_r", "head_light", box([0.06, 0.1, 0.32], [2.03, 0.66, -0.56], [0, 0, -0.35]));
add("taillight_l", "tail_light", box([0.05, 0.12, 0.28], [-2.07, 0.8, 0.6]));
add("taillight_r", "tail_light", box([0.05, 0.12, 0.28], [-2.07, 0.8, -0.6]));
add("number_plate_front", "plate", box([0.02, 0.11, 0.5], [2.1, 0.4, 0]));
add("number_plate_rear", "plate", box([0.02, 0.11, 0.5], [-2.09, 0.62, 0]));

// Cabin (right-hand drive)
add("steering_wheel", "plastic", place(new THREE.TorusGeometry(0.17, 0.022, 6, 18), [0.5, 0.98, -0.38], [0, Math.PI / 2, -0.35]));
add("airbag", "part", place(new THREE.CylinderGeometry(0.06, 0.06, 0.05, 12), [0.5, 0.98, -0.38], [0, 0, Math.PI / 2 - 0.35]));
add("instrument_cluster", "screen", box([0.03, 0.12, 0.3], [0.72, 1.06, -0.38], [0, 0, -0.3]));
add("infotainment_screen", "screen", box([0.03, 0.15, 0.26], [0.74, 1.02, 0.02], [0, 0, -0.3]));
add("ignition_switch", "metal", cylX(0.025, 0.05, [0.62, 0.9, -0.24]));

// Under the floor and the boot
add("fuel_tank", "part", box([0.5, 0.18, 0.62], [-0.95, 0.4, 0.28]));
add("adblue_tank", "plastic", box([0.2, 0.16, 0.2], [-1.55, 0.42, -0.5]));
add("cng_tank", "metal", cylZ(0.17, 1.05, [-1.62, 0.72, 0]));
add("ev_battery_pack", "plastic", box([1.7, 0.07, 1.15], [-0.05, 0.3, 0]));
add("exhaust_pipe", "metal", cylX(0.03, 2.6, [-0.25, 0.24, 0.42]));
add("silencer", "metal", cylX(0.09, 0.45, [-1.65, 0.27, 0.42]));

// ---------------------------------------------------------------- write the GLB

const missing = MESHES.filter((m) => !parts[m]);
if (missing.length) throw new Error(`no shape for: ${missing.join(", ")}`);

const doc = new Document();
const buffer = doc.createBuffer();
const mats = Object.fromEntries(
  Object.entries(MATERIALS).map(([name, m]) => [
    name,
    doc
      .createMaterial(name)
      // glTF colours are linear; THREE.Color converts the sRGB hex
      .setBaseColorFactor([...new THREE.Color(m.color).toArray(), 1] as [number, number, number, number])
      .setMetallicFactor(m.metal)
      .setRoughnessFactor(m.rough),
  ]),
) as Record<MaterialName, ReturnType<Document["createMaterial"]>>;

const scene = doc.createScene("car");
const root = doc.createNode("car");
scene.addChild(root);
for (const name of MESHES) {
  const { geo, mat } = parts[name];
  const merged = mergeGeometries(
    geo.map((g) => {
      const flat = g.index ? g.toNonIndexed() : g;
      flat.deleteAttribute("uv");
      return flat;
    }),
  );
  merged.computeBoundingBox();
  const center = merged.boundingBox!.getCenter(new THREE.Vector3());
  merged.translate(-center.x, -center.y, -center.z); // the node holds the position, so the part can be moved alone
  const pos = doc.createAccessor().setType("VEC3").setBuffer(buffer)
    .setArray(new Float32Array(merged.getAttribute("position").array));
  const nrm = doc.createAccessor().setType("VEC3").setBuffer(buffer)
    .setArray(new Float32Array(merged.getAttribute("normal").array));
  const prim = doc.createPrimitive().setAttribute("POSITION", pos).setAttribute("NORMAL", nrm).setMaterial(mats[mat]);
  const mesh = doc.createMesh(name).addPrimitive(prim);
  root.addChild(doc.createNode(name).setMesh(mesh).setTranslation([center.x, center.y, center.z]));
}

doc.createExtension(KHRDracoMeshCompression).setRequired(true);
await doc.transform(weld(), dedup(), prune(), draco({ method: "edgebreaker", quantizePosition: 14, quantizeNormal: 8 }));

const io = new NodeIO().registerExtensions([KHRDracoMeshCompression]).registerDependencies({
  "draco3d.encoder": await draco3d.createEncoderModule(),
  "draco3d.decoder": await draco3d.createDecoderModule(),
});
mkdirSync(path.dirname(OUT), { recursive: true });
await io.write(OUT, doc);
const size = statSync(OUT).size;
console.log(`wrote ${path.relative(process.cwd(), OUT)}: ${MESHES.length} parts, ${(size / 1024).toFixed(1)} KB`);
if (size > MAX_BYTES) throw new Error(`car.glb is ${size} bytes; the limit is ${MAX_BYTES}`);
