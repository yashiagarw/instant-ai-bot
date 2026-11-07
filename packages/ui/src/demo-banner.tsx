// The free demo's banner (NEXT_PUBLIC_DEMO=1, docs/deploy-free-demo.md): on every page of the website and the admin
// app, so nobody mistakes the demo for the real service. Renders nothing otherwise.

export function DemoBanner({ demo }: { demo: boolean }) {
  if (!demo) return null;
  return (
    <div
      role="note"
      aria-label="Demo"
      data-testid="demo-banner"
      className="w-full bg-ink px-4 py-2 text-center text-sm font-semibold text-white"
    >
      <span className="mr-2 rounded-full bg-white px-2 py-0.5 text-xs font-black tracking-wide text-ink uppercase">
        Demo
      </span>
      This is a demo for testing. Requests do not reach real mechanics and no one will call you. In an emergency, call
      112.
    </div>
  );
}
