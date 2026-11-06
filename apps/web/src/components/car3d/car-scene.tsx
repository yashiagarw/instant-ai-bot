"use client";

// The 3D car (Phase 5.5). Loaded only through next/dynamic (no SSR) from hero-car.tsx and result-car.tsx, so
// three.js, React Three Fiber and drei are a separate chunk that is downloaded only when 3D is shown.
// Never used in the question chat.

import { Canvas, useFrame } from "@react-three/fiber";
// drei's GLTF loader on its own (the package index would pull in all of drei).
import { useGLTF } from "@react-three/drei/core/Gltf";
import { Suspense, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { HIGHLIGHT_COLOR, SYSTEM_MESHES, type MeshName } from "@/lib/car-parts";

export const MODEL_URL = "/3d/car.glb";
// Self-hosted Draco decoder (scripts/copy-draco.mjs), never a CDN.
export const DRACO_PATH = "/draco/";

/** Panels that become see-through on the result page, so the parts inside the car can be seen. */
const SHELL = new Set<string>([
  ...SYSTEM_MESHES.body, ...SYSTEM_MESHES.doors, ...SYSTEM_MESHES.glass, ...SYSTEM_MESHES.sunroof,
  ...SYSTEM_MESHES.door_locks, ...SYSTEM_MESHES.mirrors, ...SYSTEM_MESHES.wipers,
]);
/** What the landing hero shows: the outside of the car only (the parts inside stay hidden and are not drawn). */
const EXTERIOR = new Set<string>([
  ...SHELL, ...SYSTEM_MESHES.tyres, ...SYSTEM_MESHES.wheels, ...SYSTEM_MESHES.lights, ...SYSTEM_MESHES.number_plates,
]);
const PAINT = "paint";
const BRAND_PAINT = "#F07A2A";

export interface CarSceneProps {
  mode: "hero" | "result";
  /** Meshes to show in brand orange (result page). */
  highlight?: readonly MeshName[];
  /** Turn slowly (false: still). */
  spin?: boolean;
  /** Paused while off screen. */
  paused?: boolean;
  onReady?: () => void;
}

function Car({ mode, highlight = [], spin = true, onReady }: Omit<CarSceneProps, "paused">) {
  const { scene } = useGLTF(MODEL_URL, DRACO_PATH, false);
  const group = useRef<THREE.Group>(null);

  const litKey = highlight.join(",");

  // Our own copy with our own materials, so the hero and the result page never change each other's car.
  const car = useMemo(() => {
    const copy = scene.clone(true);
    const lit = new Set<string>(litKey ? litKey.split(",") : []);
    const orange = new THREE.MeshStandardMaterial({
      color: HIGHLIGHT_COLOR,
      emissive: HIGHLIGHT_COLOR,
      emissiveIntensity: 0.6,
      roughness: 0.4,
    });
    copy.traverse((o) => {
      if (!(o instanceof THREE.Mesh)) return;
      const base = o.material as THREE.MeshStandardMaterial;
      if (mode === "hero" && !EXTERIOR.has(o.name)) {
        o.visible = false;
        return;
      }
      if (lit.has(o.name)) {
        o.material = orange;
        o.renderOrder = 2;
        o.scale.multiplyScalar(1.12); // a little larger, so a small part (a clutch disc) is easy to find
        return;
      }
      const m = base.clone();
      if (mode === "hero" && base.name === PAINT) m.color.set(BRAND_PAINT);
      if (mode === "result") {
        if (SHELL.has(o.name)) {
          m.transparent = true;
          m.opacity = 0.14;
          m.depthWrite = false;
        } else {
          m.color.lerp(new THREE.Color("#C9CDD2"), 0.35);
          if (lit.size) {
            // The other parts step back so the orange one stands out.
            m.transparent = true;
            m.opacity = 0.4;
            m.depthWrite = false;
          }
        }
      }
      o.material = m;
    });
    return copy;
  }, [scene, litKey, mode]);

  useEffect(() => {
    onReady?.();
  }, [car, onReady]);

  useFrame((_, delta) => {
    if (spin && group.current) group.current.rotation.y += Math.min(delta, 0.05) * 0.35;
  });

  return (
    <group ref={group} rotation={[0, mode === "hero" ? -0.6 : -0.9, 0]}>
      <primitive object={car} position={[0, -0.7, 0]} />
    </group>
  );
}

export default function CarScene({ paused = false, ...props }: CarSceneProps) {
  return (
    <Canvas
      aria-hidden="true"
      dpr={[1, 1.5]}
      frameloop={paused || !props.spin ? "demand" : "always"}
      camera={{ position: props.mode === "hero" ? [4.2, 1.9, 4.2] : [4.4, 2.6, 4.4], fov: 32 }}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      style={{ width: "100%", height: "100%" }}
    >
      <hemisphereLight args={["#FFF6EE", "#8A7F76", 1.6]} />
      <directionalLight position={[5, 8, 4]} intensity={2.2} />
      <directionalLight position={[-4, 3, -5]} intensity={0.6} />
      <Suspense fallback={null}>
        <Car {...props} />
      </Suspense>
    </Canvas>
  );
}
