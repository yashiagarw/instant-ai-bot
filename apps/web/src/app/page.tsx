import { Button } from "@/components/ui/button";

// Placeholder home page. The real landing page comes in task 1.7.
export default function Home() {
  return (
    <>
      <header className="border-b border-border px-4 py-4 sm:px-8">
        <p className="text-lg font-black tracking-tight text-ink">
          Instant <span className="text-orange-text">Mechanic</span>
        </p>
      </header>

      <main className="flex flex-1 flex-col items-start justify-center gap-6 bg-warm-white px-4 py-16 sm:px-8">
        <p className="rounded-full bg-brand/15 px-3 py-1 text-sm font-semibold text-orange-text">
          Coming soon
        </p>
        <h1 className="max-w-2xl font-heading text-4xl leading-[1.05] font-black tracking-tight text-ink sm:text-6xl">
          Know what&apos;s wrong with your car in 2 minutes
        </h1>
        <p className="max-w-xl text-lg text-ink/80">
          Pick your car, describe the problem, answer a few quick questions and
          get the likely causes, safety advice and an estimated repair cost.
        </p>
        <Button size="cta" type="button" aria-describedby="cta-note">
          Start free diagnosis
        </Button>
        <p id="cta-note" className="text-sm text-muted-foreground">
          The diagnosis is being built. Check back soon.
        </p>
      </main>

      <footer className="border-t border-border px-4 py-6 text-sm text-muted-foreground sm:px-8">
        Results are estimates and not a replacement for a professional
        inspection.
      </footer>
    </>
  );
}
