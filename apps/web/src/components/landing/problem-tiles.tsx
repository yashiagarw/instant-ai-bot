"use client";

import Link from "next/link";
import {
  Battery,
  BatteryLow,
  CarFront,
  CircleDot,
  ClipboardCheck,
  Cog,
  Disc,
  DoorOpen,
  Flame,
  Fuel,
  Gauge,
  KeyRound,
  type LucideIcon,
  MonitorSmartphone,
  Snowflake,
  Thermometer,
  Truck,
  Waves,
  Wrench,
  Zap,
} from "lucide-react";

import { ErrorMessage } from "@/components/error-message";
import { Skeleton } from "@/components/skeleton";
import { api, type Topic } from "@/lib/api";
import { useLoad } from "@/lib/use-load";

const ICONS: Record<string, LucideIcon> = {
  wont_start: KeyRound,
  pickup_jerking: Gauge,
  overheating_leaks: Thermometer,
  ac: Snowflake,
  clutch_gearbox: Cog,
  brakes_steering: Disc,
  suspension_noise: Wrench,
  tyres: CircleDot,
  battery_lights: Battery,
  fuel_cng_diesel: Fuel,
  ev_hybrid: Zap,
  body_doors: DoorOpen,
  screen_airbag: MonitorSmartphone,
  battery_dead: BatteryLow,
  flat_tyre: CircleDot,
  out_of_fuel: Fuel,
  locked_out: KeyRound,
  car_stuck: CarFront,
  car_in_water: Waves,
  accident_tow: Truck,
  smoke: Flame,
  book_inspection: ClipboardCheck,
};

export function TopicIcon({ code, className }: { code: string; className?: string }) {
  const Icon = ICONS[code] ?? Wrench;
  return <Icon aria-hidden="true" className={className} />;
}

type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; topics: Topic[] };

function TopicLink({ topic, emergency = false }: { topic: Topic; emergency?: boolean }) {
  const Icon = ICONS[topic.code] ?? Wrench;
  return (
    <Link
      href={`/diagnose?topic=${encodeURIComponent(topic.code)}`}
      className={
        emergency
          ? "flex min-h-12 items-center gap-2 rounded-full border-2 border-ink/15 bg-white px-4 py-2 font-semibold text-ink outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring"
          : "flex h-full min-h-24 flex-col items-start justify-between gap-3 rounded-3xl border border-border bg-white p-4 font-bold text-ink outline-none hover:border-cta focus-visible:ring-3 focus-visible:ring-ring"
      }
    >
      <Icon aria-hidden="true" className={emergency ? "size-5 text-orange-text" : "size-7 text-orange-text"} />
      <span>{topic.label}</span>
    </Link>
  );
}

/** Problem tiles and the emergency row, from GET /api/categories. */
export function ProblemTiles() {
  const { state: load, retry } = useLoad("categories", (signal) => api.categories(signal));
  const state: State = load.status === "ready" ? { status: "ready", topics: load.data.topics } : load;

  const tiles = state.status === "ready" ? state.topics.filter((t) => t.type === "tile") : [];
  const urgent = state.status === "ready" ? state.topics.filter((t) => t.type !== "tile") : [];

  return (
    <>
      <section aria-labelledby="emergency-heading" className="mx-auto max-w-6xl px-4 py-8 sm:px-8">
        <h2 id="emergency-heading" className="text-2xl font-black tracking-tight text-ink">
          Need help right now?
        </h2>
        <p className="mt-1 text-ink/75">Stuck on the road? Get safety steps and ask for a mechanic.</p>
        <div className="mt-4" aria-busy={state.status === "loading"}>
          {state.status === "loading" && (
            <div className="flex flex-wrap gap-2">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-12 w-36 rounded-full" />
              ))}
            </div>
          )}
          {state.status === "ready" && (
            <ul className="flex flex-wrap gap-2">
              {urgent.map((t) => (
                <li key={t.code}>
                  <TopicLink topic={t} emergency />
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section aria-labelledby="tiles-heading" className="mx-auto max-w-6xl px-4 py-8 sm:px-8">
        <h2 id="tiles-heading" className="text-3xl font-black tracking-tight text-ink sm:text-4xl">
          What&apos;s the problem?
        </h2>
        <div className="mt-6" aria-busy={state.status === "loading"}>
          {state.status === "loading" && (
            <>
              <span className="sr-only" role="status">
                Loading problems…
              </span>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {Array.from({ length: 8 }, (_, i) => (
                  <Skeleton key={i} className="h-24 rounded-3xl" />
                ))}
              </div>
            </>
          )}
          {state.status === "error" && <ErrorMessage message={state.message} onRetry={retry} />}
          {state.status === "ready" && (
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {tiles.map((t) => (
                <li key={t.code}>
                  <TopicLink topic={t} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </>
  );
}
