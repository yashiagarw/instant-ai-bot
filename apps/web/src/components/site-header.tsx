import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-warm-white/90 backdrop-blur">
      <div className="mx-auto flex min-h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-8">
        <Link
          href="/"
          className="inline-flex min-h-11 items-center rounded-full text-xl font-black tracking-tight text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring"
        >
          Instant&nbsp;<span className="text-orange-text">Mechanic</span>
        </Link>
        <span className="hidden text-sm font-semibold text-ink/70 sm:inline">AI car diagnosis · Delhi NCR</span>
      </div>
    </header>
  );
}
