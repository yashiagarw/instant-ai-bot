# apps/web

Customer site: Next.js (App Router) + TypeScript + Tailwind CSS v4 + shadcn/ui.

```bash
cp .env.example .env.local
pnpm install
pnpm dev          # http://localhost:3000
pnpm test         # Vitest component tests, single run
pnpm test:watch
pnpm test:e2e     # Playwright, phone (Pixel 7) and desktop (1280px); builds and starts the app on port 3100
                  # first time only: pnpm exec playwright install chromium
pnpm lint
pnpm build
```

Brand colour tokens live in `src/app/globals.css` (`bg-brand`, `bg-cta`, `text-orange-text`, `text-ink`, `bg-warm-white`, `text-danger`). shadcn's `primary` is the CTA fill and `destructive` is the safety red. Use `<Button size="cta">` for the main call to action.

## Pages

- `/`: landing page. Problem tiles and the emergency row come from `GET /api/categories`.
- `/diagnose`: step 1 (Car). Search (`/api/vehicles/search`, debounced), make tiles, then model, year, fuel and
  gearbox from the catalogue. "My car isn't listed" asks for make, model, year, fuel, gearbox and rough price.
  The choice is saved in sessionStorage (`im.diagnosis.vehicle`) for the Problem step.

- `/diagnose/[sessionId]`: the questions, one at a time. `/diagnose/[sessionId]/result`: the result (shareable).
- Hindi (Phase 5.5): `/hi`, `/hi/diagnose`, `/hi/diagnose/[sessionId]` and `/hi/diagnose/[sessionId]/result`. The pages
  live in `src/app/[locale]/`; English addresses are rewritten to `/en/…` in `next.config.ts`. Messages:
  `src/i18n/messages/` (Hindi drafts to review: `docs/hindi-review.md`).
- 3D car: `src/components/car3d/` (loaded with next/dynamic, never in the chat), parts per category in
  `src/lib/car-parts.ts`, model built by `pnpm build:car`, skipped by `src/lib/three-d.ts`.
- `/request?session=…`: Request a Mechanic, prefilled from the diagnosis; urgent for emergencies; confirmation
  with a reference number. The consent wording and the helpline come from `GET /api/service-requests/config`.

The backend must be running for live data (`cd backend && uv run uvicorn app.main:app --reload`), and its CORS
allows only `WEB_ORIGIN` (default `http://localhost:3000`). The Playwright tests mock the API and need no backend.
