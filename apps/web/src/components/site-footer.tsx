import Link from "next/link";

export const DISCLAIMER =
  "Results are estimates based on your answers and our data. They are not a replacement for a professional inspection by a mechanic.";

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-sm text-muted-foreground sm:px-8">
        <p className="font-semibold text-ink">
          Instant <span className="text-orange-text">Mechanic</span> · Delhi NCR
        </p>
        <p>{DISCLAIMER}</p>
        <p>In an emergency or if you feel unsafe, move away from the car and call 112.</p>
        <nav aria-label="Legal" className="flex flex-wrap gap-x-5">
          <Link href="/privacy" className="inline-flex min-h-11 items-center font-semibold text-ink underline underline-offset-4">
            Privacy notice
          </Link>
          <Link href="/terms" className="inline-flex min-h-11 items-center font-semibold text-ink underline underline-offset-4">
            Terms of use
          </Link>
          <Link href="/disclaimer" className="inline-flex min-h-11 items-center font-semibold text-ink underline underline-offset-4">
            Disclaimer
          </Link>
        </nav>
      </div>
    </footer>
  );
}
