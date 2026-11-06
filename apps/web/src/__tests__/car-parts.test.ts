import { readFileSync, statSync } from "node:fs";
import path from "node:path";
import { expect, test } from "vitest";

import { CATEGORY_SYSTEMS, HIGHLIGHT_COLOR, highlightMeshes, MESHES, SYSTEM_MESHES } from "@/lib/car-parts";

const ROOT = path.join(__dirname, "../../../..");
const GLB = path.join(__dirname, "../../public/3d/car.glb");

/** Category codes from data/schema/taxonomy.yaml (the `categories:` list). */
function taxonomyCategories(): string[] {
  const yaml = readFileSync(path.join(ROOT, "data/schema/taxonomy.yaml"), "utf8");
  const from = yaml.indexOf("\ncategories:");
  const rest = yaml.slice(from + 1);
  const body = rest.slice(rest.indexOf("\n"));
  const next = body.search(/^[a-z_]+:/m); // the next top-level key
  const block = next < 0 ? body : body.slice(0, next);
  return [...block.matchAll(/^ {2}- code: (\w+)/gm)].map((m) => m[1]);
}

/** The JSON chunk of a GLB (node and mesh names; geometry is Draco-compressed in the binary chunk). */
function glbJson(file: string) {
  const buf = readFileSync(file);
  expect(buf.readUInt32LE(0)).toBe(0x46546c67); // "glTF"
  const len = buf.readUInt32LE(12);
  return JSON.parse(buf.subarray(20, 20 + len).toString("utf8")) as {
    nodes: { name?: string; mesh?: number }[];
    extensionsUsed?: string[];
    extensionsRequired?: string[];
  };
}

test("every fault category in the taxonomy is mapped (to systems, or null = no clear part)", () => {
  const codes = taxonomyCategories();
  expect(codes.length).toBe(41);
  expect(Object.keys(CATEGORY_SYSTEMS).sort()).toEqual([...codes].sort());
  for (const systems of Object.values(CATEGORY_SYSTEMS)) {
    for (const s of systems ?? []) expect(Object.keys(SYSTEM_MESHES)).toContain(s);
  }
});

test("categories with no clear part (no highlight)", () => {
  const none = Object.entries(CATEGORY_SYSTEMS).filter(([, v]) => v === null).map(([k]) => k).sort();
  expect(none).toEqual(["inspection", "not_starting", "sensor_ecu", "smoke_fire", "stuck", "towing_accident", "waterlogging"]);
  expect(highlightMeshes("sensor_ecu")).toEqual([]);
  expect(highlightMeshes("unknown_category")).toEqual([]);
  expect(highlightMeshes("clutch")).toEqual(["clutch"]);
  expect(HIGHLIGHT_COLOR).toBe("#F07A2A");
});

test("car.glb: Draco-compressed, under 1.5 MB, with a node for every mesh name in the config", () => {
  expect(statSync(GLB).size).toBeLessThan(1.5 * 1024 * 1024);
  const gltf = glbJson(GLB);
  expect(gltf.extensionsRequired).toContain("KHR_draco_mesh_compression");
  const names = new Set(gltf.nodes.filter((n) => n.mesh !== undefined).map((n) => n.name));
  const missing = MESHES.filter((m) => !names.has(m));
  expect(missing, `car.glb has no node for: ${missing.join(", ")}`).toEqual([]);
});
