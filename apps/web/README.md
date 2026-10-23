# apps/web

Customer site: Next.js (App Router) + TypeScript + Tailwind CSS v4 + shadcn/ui.

```bash
cp .env.example .env.local
pnpm install
pnpm dev          # http://localhost:3000
pnpm test         # Vitest, single run
pnpm test:watch
pnpm lint
pnpm build
```

Brand colour tokens live in `src/app/globals.css` (`bg-brand`, `bg-cta`, `text-orange-text`, `text-ink`, `bg-warm-white`, `text-danger`). shadcn's `primary` is the CTA fill and `destructive` is the safety red. Use `<Button size="cta">` for the main call to action.
