// Car systems for the 3D car (Phase 5.5): which meshes of public/3d/car.glb make up each system, and which system
// each fault category (data/schema/taxonomy.yaml) points at. The result page highlights the diagnosed category's
// meshes in brand orange.
//
// Swapping the model: a designer's GLB can replace public/3d/car.glb as long as it has nodes (or meshes) with the
// names in MESHES below. Extra meshes are fine. A missing one is skipped (nothing is highlighted for it), and the
// test in src/__tests__/car-parts.test.ts lists the names the file does not have. The generic car is built by
// scripts/build-car-model.ts (`pnpm build:car`).
//
// Plain TypeScript with no imports: the build script runs it with Node's type stripping.

/** Every named part of the car, grouped by system. */
export const SYSTEM_MESHES = {
  body: ["body_shell", "bumper_front", "bumper_rear"],
  doors: ["door_fl", "door_fr", "door_rl", "door_rr", "bonnet", "boot_lid"],
  door_locks: ["door_handle_fl", "door_handle_fr", "door_handle_rl", "door_handle_rr"],
  glass: ["windscreen", "rear_glass", "side_glass_l", "side_glass_r"],
  sunroof: ["sunroof"],
  wipers: ["wiper_l", "wiper_r"],
  mirrors: ["mirror_l", "mirror_r", "irvm"],
  tyres: ["tyre_fl", "tyre_fr", "tyre_rl", "tyre_rr"],
  wheels: ["wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"],
  brakes: [
    "brake_disc_fl", "brake_disc_fr", "brake_disc_rl", "brake_disc_rr",
    "brake_caliper_fl", "brake_caliper_fr", "brake_caliper_rl", "brake_caliper_rr",
  ],
  suspension: ["suspension_fl", "suspension_fr", "suspension_rl", "suspension_rr"],
  steering: ["steering_wheel", "steering_rack"],
  airbag: ["airbag"],
  dashboard: ["instrument_cluster"],
  infotainment: ["infotainment_screen"],
  ignition: ["ignition_switch"],
  engine: ["engine"],
  spark_plugs: ["spark_plugs"],
  throttle: ["throttle_body"],
  engine_belt: ["engine_belt"],
  cooling: ["radiator", "cooling_hose"],
  ac: ["ac_compressor", "ac_condenser"],
  battery: ["battery"],
  starter: ["starter_motor"],
  electrical: ["fuse_box", "wiring_harness"],
  lights: ["headlight_l", "headlight_r", "taillight_l", "taillight_r"],
  horn: ["horn"],
  clutch: ["clutch"],
  gearbox: ["gearbox", "drive_shaft"],
  exhaust: ["exhaust_pipe", "silencer"],
  fuel: ["fuel_tank"],
  adblue: ["adblue_tank"],
  cng: ["cng_tank"],
  ev_battery: ["ev_battery_pack"],
  underbody: ["underbody_shield"],
  number_plates: ["number_plate_front", "number_plate_rear"],
} as const satisfies Record<string, readonly string[]>;

export type CarSystem = keyof typeof SYSTEM_MESHES;
export type MeshName = (typeof SYSTEM_MESHES)[CarSystem][number];

/** All mesh names the model is expected to have. */
export const MESHES: readonly MeshName[] = Object.values(SYSTEM_MESHES).flat();

/** Fault category code -> the systems to highlight. null: no single clear part (general or whole-car problems), so
 * the car is shown without a highlight. Every category in taxonomy.yaml is listed (checked by a test). */
export const CATEGORY_SYSTEMS: Record<string, readonly CarSystem[] | null> = {
  clutch: ["clutch"],
  cooling: ["cooling"],
  steering: ["steering"],
  tyre: ["tyres"],
  ac: ["ac"],
  ev_hybrid: ["ev_battery"],
  self_start: ["starter"],
  stuck: null,
  battery: ["battery"],
  pickup_throttle: ["throttle"],
  not_starting: null,
  fuel_delivery: ["fuel"],
  dashboard_warning: ["dashboard"],
  engine_belt: ["engine_belt"],
  brakes: ["brakes"],
  engine: ["engine"],
  electrical: ["electrical"],
  lights_horn: ["lights", "horn"],
  ignition_key: ["ignition"],
  underbody: ["underbody"],
  starter_motor: ["starter"],
  mirror: ["mirrors"],
  inspection: null,
  suspension: ["suspension"],
  door_boot_bonnet: ["doors"],
  window_wiper: ["glass", "wipers", "sunroof"],
  jerking_misfire: ["spark_plugs", "throttle"],
  sensor_ecu: null,
  infotainment: ["infotainment"],
  airbag_srs: ["airbag"],
  hose_leak: ["cooling"],
  exhaust: ["exhaust"],
  smoke_fire: null,
  gearbox: ["gearbox"],
  key_lockout: ["door_locks"],
  cng: ["cng"],
  diesel: ["fuel", "adblue"],
  body: ["body", "doors"],
  waterlogging: null,
  number_plate: ["number_plates"],
  towing_accident: null,
};

/** The meshes to highlight for a category ([] when it has no clear part or is unknown). */
export function highlightMeshes(category: string | null | undefined): MeshName[] {
  const systems = category ? CATEGORY_SYSTEMS[category] : null;
  return systems ? systems.flatMap((s) => [...SYSTEM_MESHES[s]]) : [];
}

/** Brand orange for the highlighted part (a 3D surface, not text: the accessible text shades are #D9620F / #B4500D). */
export const HIGHLIGHT_COLOR = "#F07A2A";
