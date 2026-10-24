import { CarFront, ClipboardCheck, MessageSquareText } from "lucide-react";

const STEPS = [
  { icon: CarFront, title: "Pick your car", text: "Search for your car or choose the make, model and year." },
  { icon: MessageSquareText, title: "Tell us the problem", text: "Choose a problem and answer one quick question at a time." },
  {
    icon: ClipboardCheck,
    title: "Get your result",
    text: "See the likely causes, what is safe to do, and the estimated cost for your car.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" aria-labelledby="how-heading" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-12 sm:px-8">
      <h2 id="how-heading" className="text-3xl font-black tracking-tight text-ink sm:text-4xl">
        How it works
      </h2>
      <ol className="mt-6 grid gap-4 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="flex gap-4 rounded-3xl border border-border bg-white p-5">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-cta text-xl font-black text-white">
              {i + 1}
            </span>
            <div>
              <h3 className="flex items-center gap-2 text-lg font-bold text-ink">
                <s.icon aria-hidden="true" className="size-5 text-orange-text" />
                {s.title}
              </h3>
              <p className="mt-1 text-ink/75">{s.text}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
