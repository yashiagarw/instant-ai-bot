# Instant Mechanic: AI car diagnosis

AI car diagnosis chatbot and mechanic assistance platform for [Instant Mechanic](https://instantmechanic.online), Delhi NCR. Project rules are in [CLAUDE.md](CLAUDE.md).

## Layout

| Path | What |
|---|---|
| `apps/web` | Customer site (port 3000): Next.js (App Router), TypeScript, Tailwind CSS v4, shadcn/ui |
| `apps/admin` | Staff admin app (port 3001): sign-in with two-factor, role-based menu, Users, Audit log |
| `packages/ui` | `@im/ui`, shared by both apps: brand theme, Button, Dialog, the data table (TanStack Table) |
| `backend/app` | FastAPI app. Modules: `vehicles`, `knowledge`, `diagnosis`, `requests`, `accounts` (phone + OTP login), `uploads` (customer photos), `notify` (email and SMS), `llm` (optional LLM layer, off by default), `parts` (parts catalogue), `datasets` (dataset publish pipeline and its worker) |
| `backend/engine` | Diagnosis engine, plain Python with no web imports |
| `backend/alembic` | Database migrations |
| `data/raw` | The 18 original Excel datasets. Never edit |
| `data/schema` | Manifest, column aliases, taxonomy, import rules, CSV templates for price sources (`templates/`) |
| `data/catalogue` | Vehicle catalogue seed (editable YAML); team price sources in `parts/` |
| `docs` | Dataset profile, findings, data model, [how the engine and LLM layer work](docs/diagnosis-engine.md), [adding a category](docs/adding-a-category.md), [fine-tuning the search model](docs/embedding-model.md) |
| `scripts` | Offline data scripts (dataset profiler) |
| `docker-compose.yml` | Development: PostgreSQL 16 + pgvector, S3-compatible storage for photos (SeaweedFS), Redis for background jobs; the apps with hot reload under the `app` profile |
| `docker-compose.prod.yml`, `docker/caddy` | Production stack behind Caddy with automatic HTTPS ([Phase 5.1](#phase-51-containers-and-production)) |
| `backend/Dockerfile`, `apps/Dockerfile` | Production images: API + worker (one image), web / admin |

## Requirements

- Docker (with Compose)
- [uv](https://docs.astral.sh/uv/) for Python (it installs Python 3.12 if needed)
- Node.js 20+ and [pnpm](https://pnpm.io)

## Phase 1 run guide

Phase 1 is the customer flow: pick a car → pick a problem → answer one question at a time → result with
likely causes, safety advice and segment costs → Request a Mechanic (stored with consent, emailed to support).

### 1. First-time setup

```bash
# Env files. The defaults work for local development; set HELPLINE_NUMBER and SUPPORT_EMAIL in backend/.env.
cp .env.example .env
cp backend/.env.example backend/.env
cp apps/web/.env.example apps/web/.env.local

# Database: PostgreSQL 16 + pgvector, plus an autocare_test database for pytest; photo storage (S3, SeaweedFS);
# Redis for the background worker (dataset publish pipeline)
docker compose up -d db storage redis

# Backend and data (run in this order)
cd backend
uv sync
uv run alembic upgrade head                          # all migrations (0001 … 0021)
uv run python -m app.vehicles.seed                   # vehicle catalogue from data/catalogue/vehicles.yaml
uv run python -m app.knowledge.importer --all        # the 18 datasets (first run downloads a ~470 MB model)
uv run python -m app.knowledge.questions load --all  # approved question flows + safety rules (data/review/questions)
uv run python -m app.knowledge.merges apply          # approved duplicate-fault merges (data/review/merges.yaml)
uv run python -m app.knowledge.requirements apply    # what faults need (start-stop, diesel, AMT …): data/review/fault_requirements.yaml
uv run python -m app.knowledge.phrases load          # reviewed extra customer phrases (spellings, Hindi): data/review/phrases
uv run python -m app.knowledge.safety_triggers apply # reviewed phrases for global emergency rules: data/review/safety_global_triggers.yaml
uv run python -m app.uploads.storage setup           # private photo bucket (needs S3_ACCESS_KEY / S3_SECRET_KEY in backend/.env)
uv run python -m app.vision.catalogue seed           # photo labels (warning lights, damage): data/review/image_labels.yaml
uv run python -m app.knowledge.embeddings sync       # search index: embeds only new or changed texts
uv run python -m app.parts build                     # parts catalogue (after merges): prices, fits, fault links, labour
cd ..
# After this first import, publish it once on the admin Datasets page (or keep using these commands): from then on
# a category file is uploaded there, and the worker runs every step above automatically (Phase 4.3).

# Web apps (one pnpm workspace at the repo root: apps/web, apps/admin, packages/ui)
pnpm install                                          # from the repo root
pnpm --filter web exec playwright install chromium    # once, for the end-to-end tests
```

After pulling new code, run `uv run alembic upgrade head` again, and restart `pnpm dev` after any `pnpm install`.

### 2. Run

Three terminals: the API, the background worker, then both web apps together.

```bash
docker compose up -d db storage redis
cd backend && uv run uvicorn app.main:app --reload --port 8000
# http://localhost:8000/api/health  ->  {"status":"ok","database":"ok"}
# http://localhost:8000/docs        ->  API docs with request and response schemas
```

```bash
cd backend && uv run arq app.datasets.worker.WorkerSettings   # background jobs (Datasets page): build, eval, publish
# restart it after changing backend code (arq has no --reload); Ctrl+C waits for the running job to finish
```

```bash
pnpm dev            # from the repo root: the website and the admin app side by side
# http://localhost:3000   customer website  (WEB_ORIGIN)
# http://localhost:3001   staff admin app   (ADMIN_ORIGIN)
```

The API's CORS allows exactly these two addresses, so keep the ports. One app only: `pnpm dev:web` or
`pnpm dev:admin` (or `cd apps/web && pnpm dev` as before). Both read `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`) from their own `.env.local`.

### 3. Try the flow

1. **Home** (`/`): problem tiles and the emergency row come from the API. Press **Start free diagnosis**.
2. **Car** (`/diagnose`): search ("swift 2019 petrol"), or pick make → model → year → fuel → gearbox. Or choose
   **My car isn't listed** and type it in (with "Not sure" for the price, the result shows General guidance).
3. **Problem**: tap a tile (English + Hindi; untuned categories show **Beta**), an **Emergency help** topic, or
   describe the problem in your own words.
4. **Questions** (`/diagnose/{session}`): one card at a time, **Not sure**, **Back**, "Question 3 of about 8".
   Red safety banners appear the moment the API returns them. Emergency topics ask at most 3 questions.
5. **Result** (`/diagnose/{session}/result`, shareable): safety banner (high-risk rules only), coverage badge,
   roadside verdict and towing, segment cost with approx label and price-check date, illustrations, what you can
   do / what the mechanic will do, other causes, disclaimer, feedback, **Request a Mechanic**.
6. **Request** (`/request?session={session}`): prefilled with the car and diagnosis; unticked consent box.
   Emergencies are marked urgent, show the helpline first and skip optional fields. The confirmation shows the
   reference number. With the default console email provider, the alert email is printed in the API terminal.

Useful checks: `docker compose exec db psql -U autocare -d autocare -c "select reference, status, urgent,
consent_text_version, consent_at, alert_sent_at, alert_error from service_requests order by created_at desc limit 5;"`

### 4. Test

```bash
docker compose up -d db                      # backend tests need the database
cd backend && uv run pytest -q               # API, engine, importer, migrations, requests
cd backend && uv run ruff check . && uv run ruff format --check .
cd backend && uv run python ../data/eval/run_eval.py --simulate   # diagnosis quality on golden + simulated cases
cd backend && uv run python ../data/eval/run_eval.py run --split test --extraction llm   # through the LLM extraction step (fallback when LLM_PROVIDER=none)
pnpm test                                    # Vitest in packages/ui, apps/web and apps/admin (from the repo root)
cd apps/web && pnpm test:e2e                 # Playwright, phone + desktop (builds and serves the app on :3100;
                                             # the API is mocked, no backend needed)
cd apps/admin && pnpm test:e2e               # admin: login, two-factor setup, menus by role, Users, Audit (:3101)
# If Playwright times out on a busy machine: add --workers=1 (pnpm exec playwright test --workers=1)
# Optional: the same flows against the real API and database, LLM off (own ports, so `pnpm dev` keeps working):
cd backend && LLM_PROVIDER=none WEB_ORIGIN=http://localhost:3110 uv run uvicorn app.main:app --port 8010
cd apps/web && E2E_LIVE_API=1 E2E_PORT=3110 NEXT_PUBLIC_API_URL=http://localhost:8010 pnpm exec playwright test e2e/live.spec.ts
pnpm lint && pnpm build                      # both apps (and a type check of packages/ui)
```

Data scripts (dataset profiler, schema file checks):

```bash
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python -m pytest scripts/tests -q
.venv/bin/python scripts/profile_datasets.py --out docs/dataset-check.md
```

## Database

- Connection settings: root `.env` (container) and `backend/.env` (`DATABASE_URL`, `TEST_DATABASE_URL`). Keep them in sync.
- The test database is created by `docker/postgres/init/` the first time the volume is created. If you created the volume before that script existed, run `docker compose down -v && docker compose up -d db` (this deletes local data).
- pytest refuses to run against a database whose name does not end in `_test`.
- Vehicle catalogue: edit `data/catalogue/vehicles.yaml`, then `cd backend && uv run python -m app.vehicles.seed` (safe to re-run; add `--prune` to delete entries removed from the file).
- Dataset import: `cd backend && uv run python -m app.knowledge.importer --all` (or `--file "data/raw/TYRE CATEGORY 4.xlsx"`). Safe to re-run: the same inputs replace the same dataset version. `--no-embeddings` is faster but leaves re-imported phrases and symptoms without vectors. Outputs for people to review go to `data/review/` (import report, costs.csv, duplicates.csv, review_items.csv, and `costs/F02-labour.yaml`, where Overheating labour is approved). Extracted pictures go to `data/media/` (not in git; the importer regenerates them).
- New migration: `cd backend && uv run alembic revision -m "describe change"` (autogenerate works once models exist: add `--autogenerate`). Never edit an applied migration.

## Environment variables

| File | Variable | Purpose |
|---|---|---|
| `.env` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_TEST_DB`, `POSTGRES_PORT` | Database container |
| `backend/.env` | `DATABASE_URL` | SQLAlchemy URL (psycopg 3) |
| | `TEST_DATABASE_URL` | pytest database (must end in `_test`) |
| | `WEB_ORIGIN`, `ADMIN_ORIGIN` | The two origins CORS allows: the website (`http://localhost:3000`) and the admin app (`http://localhost:3001`) |
| | `DB_CONNECT_TIMEOUT` | Seconds before the health check reports the database down |
| | `ENVIRONMENT` | `development` / `test` / `production` |
| | `SESSION_RATE_LIMIT`, `SESSION_RATE_WINDOW_SECONDS` | New diagnosis sessions per IP per window |
| | `TRUST_FORWARDED_FOR` | Use X-Forwarded-For for the client IP (only behind your own proxy) |
| | `DIAGNOSIS_ENGINE` | `v2` (default: Bayesian posterior over faults, next question by information gain) or `v1` (the earlier score-based engine) |
| | `DIAGNOSIS_SEARCH` | Free-text matching: `hybrid` (default: keyword index plus full-text + vector + typo search over the `embeddings` table; loads the local multilingual MiniLM model, ~470 MB, at first use) or `keyword` |
| | `EMBEDDING_MODEL` | Model for new search vectors: the original multilingual MiniLM (default) or a fine-tuned folder in `data/models` (e.g. `minilm-im-v1`). Only new dataset builds use it; each version keeps its own model, so a new one goes live through a draft, the eval gate and publish ([docs/embedding-model.md](docs/embedding-model.md)) |
| | `MEDIA_DIR` | Fault pictures served at `/media` (default `data/media`) |
| | `HELPLINE_NUMBER` | Helpline shown on the request form and confirmation (placeholder in `.env.example`) |
| | `SUPPORT_EMAIL` | New requests are emailed here; empty = no alert (the request is still stored) |
| | `EMAIL_PROVIDER` | `console` (default, prints the email), `smtp` or `resend` |
| | `EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `RESEND_API_KEY` | Email provider settings |
| | `REQUEST_RATE_LIMIT`, `REQUEST_RATE_WINDOW_SECONDS` | New service requests per IP per window |
| | `AUTH_SECRET` | Keys the OTP hashes; a long random value in production (required there) |
| | `SMS_PROVIDER` | `console` (default, prints login codes; development only) or `msg91` |
| | `MSG91_AUTH_KEY`, `MSG91_TEMPLATE_ID`, `MSG91_SENDER_ID` | MSG91 OTP sending (placeholders; see "Going live with MSG91") |
| | `OTP_TTL_SECONDS`, `OTP_MAX_ATTEMPTS`, `OTP_PHONE_LIMIT`, `OTP_PHONE_WINDOW_SECONDS`, `OTP_IP_LIMIT`, `OTP_IP_WINDOW_SECONDS`, `OTP_VERIFY_IP_LIMIT`, `OTP_VERIFY_IP_WINDOW_SECONDS` | Code lifetime, tries and rate limits |
| | `AUTH_SESSION_DAYS`, `COOKIE_SECURE` | Login length; Secure flag on cookies (keep true) |
| | `STAFF_TOTP_KEY` | Encrypts staff two-factor secrets (a Fernet key; placeholder in `.env.example`, required in production; changing it means everyone sets up two-factor again) |
| | `STAFF_SESSION_HOURS`, `STAFF_IDLE_MINUTES`, `STAFF_MAX_FAILED_LOGINS`, `STAFF_LOCKOUT_MINUTES`, `STAFF_LOGIN_IP_LIMIT`, `STAFF_LOGIN_IP_WINDOW_SECONDS` | Staff sessions (8 h, 30 min idle), lockout (5 failures, 15 min) and sign-in rate limit per IP |
| | `UPLOADS_DIR` | Customer files outside the bucket (none yet), one folder per user, deleted with the account |
| | `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Photo storage key pair (placeholders in `.env.example`; the local `storage` container reads the same pair) |
| | `S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET` | Where the API reaches the storage, the address in links given to browsers, region, private bucket |
| | `UPLOAD_MAX_BYTES`, `UPLOAD_MAX_PX`, `UPLOAD_URL_TTL_SECONDS`, `UPLOAD_VIEW_TTL_SECONDS`, `UPLOADS_PER_SESSION`, `UPLOAD_RATE_LIMIT`, `UPLOAD_RATE_WINDOW_SECONDS` | 10 MB, 2000 px, upload-form and view-link lifetimes, photos per diagnosis, uploads per IP |
| | `LLM_PROVIDER` | `none` (default: no LLM calls, every step uses its fallback), `anthropic` (live LLM layer, only with `ANTHROPIC_API_KEY`) or `openai` (offline question drafting only). See [LLM layer](#llm-layer-off-by-default) |
| | `ANTHROPIC_API_KEY` | Claude API key: empty in `.env.example`; set it only to switch the LLM layer on |
| | `LLM_EXTRACTION_MODEL`, `LLM_PHRASING_MODEL`, `LLM_EXPLANATION_MODEL`, `LLM_EFFORT` | Live LLM models (`claude-haiku-5-5`) and effort (`low`) |
| | `LLM_TIMEOUT_SECONDS`, `LLM_DAILY_SPEND_CAP_USD` | Per-call wall-clock timeout (4 s) and daily estimated spend cap (USD, India-time day); past either, the fallback is used |
| | `LLM_VISION_MODEL`, `LLM_VISION_TIMEOUT_SECONDS`, `VISION_MIN_CONFIDENCE` | Photo analysis: model (`claude-opus-5-5`), timeout (20 s), and the confidence below which a finding counts as unclear (0.6). Same switch and spend cap as above |
| | `QUESTIONS_MODEL`, `QUESTIONS_EFFORT`, `OPENAI_API_KEY`, `OPENAI_MODEL`, … | Offline question drafting (`python -m app.knowledge.questions`, `--provider anthropic\|openai`) |
| | `REDIS_URL` | Redis for background jobs (`redis://localhost:6379/0`; `docker compose up -d redis`) |
| | `DATASET_UPLOAD_DIR`, `DATASET_UPLOAD_MAX_MB` | Where uploaded dataset files are kept (default `data/uploads/datasets`, not committed; versions are rebuilt and rolled back from them) and the upload limit (25 MB) |
| `apps/web/.env.local` | `NEXT_PUBLIC_API_URL` | Backend base URL for the browser |

## Phase 2.5: explanations, typed replies, car features

How it all works: [docs/diagnosis-engine.md](docs/diagnosis-engine.md). With `LLM_PROVIDER=none` (the default)
everything below works without any API key:

- **Chat**: customers can type a reply at any time (`POST /api/diagnosis/sessions/{id}/messages`). A "We understood:
  …" chip shows what was taken from it; tapping it offers "Edit my message", which takes the message back
  (`POST …/messages/undo`) until an option is tapped.
- **Result**: each cause shows a confidence word (High / Medium / Low) with a 3-step meter and the reason, its evidence
  (what fits and what doesn't), a short explanation streamed over server-sent events
  (`GET …/explanations`; templates with the LLM off), uncertainty messages and "If this doesn't fix it".
- **Safety tips** are full, calm sentences; workshop-only lines are never shown
  (`uv run python -m app.diagnosis.safety_lines report` lists every dataset line and what customers see; reviewed
  rewrites: `data/review/safety_tips.yaml`).
- **Car features**: faults the car cannot have (start-stop on an Alto K10, CNG faults on a petrol car, AMT faults on
  a manual) are down-ranked. Feature data per model goes into `data/catalogue/vehicles.yaml`; what is still missing is
  listed in docs/diagnosis-engine.md.
- **Generated questions**: with the LLM on, questions it proposes when nothing fits are saved to `generated_questions`
  for review and never asked.

## Phase 3.1: parts catalogue

Built from the price sheets by `cd backend && uv run python -m app.parts build` (re-run after every re-import and after
`merges apply`; it prints what was loaded per file). Tables (migration 0010): `part_types`, `brands` (oem / oes /
aftermarket), `parts`, `part_images`, `part_compatibility`, `part_prices`, `fault_parts`, `labour_rates`.

- **Price sheets** (files 9, 12, 14, 18): PARTS_PRICE_SOURCES rows become parts, prices (basis, GST, fitting, supplier,
  source URL, date, verification) and pictures (Picture ID). "Fault IDs using it" gives the fault links; file 9 has no
  such column, so its links are drafts in `data/review/parts/F09-fault-links.csv` until someone types yes in `approved`.
  Links follow `data/review/merges.yaml` to the canonical fault. LABOUR_PRICE_RESEARCH / LABOUR_AND_RECOVERY_RESEARCH
  become one labour rate per repair, segment and city (0 = does not apply, skipped).
- **Fit**: "Vehicle (fit)" text becomes a `part_compatibility` row only when it names a model in the vehicle catalogue
  (with years, fuel and gearbox when given), status `listed` or `confirm_fit` ("confirm by VIN"). "Mid-range car -
  check fit", "Any car" and models outside the catalogue give none; those are listed in `data/review/parts/fit-unmatched.csv`.
  **No part is shown as fitting a car without a compatibility record for that car.**
- **Other files** (1-8, 10, 11, 13, 15-17): `uv run python -m app.parts review` writes their segment parts columns
  (file 5: PRICE BREAKDOWN) to `data/review/parts/F01.csv` … one row per part and segment, marked "not model-verified".
  Approved rows (`approved` = yes) are loaded by `build` as segment prices; re-running `review` keeps decisions and edits.
- **Team price sources**: copy `data/schema/templates/part_price_sources.csv` / `labour_rates.csv` to
  `data/catalogue/parts/F07-part_price_sources.csv` (etc.); `build` reads them like the sheets. Columns:
  `data/schema/templates/README.md`.

API (customer-safe; source refs and review status stay internal):

| Endpoint | What |
|---|---|
| `GET /api/faults/{key}/parts?variant_id=` | Parts listed for the car first (`fit.status` `listed`, then `confirm_fit`), then the car's segment parts with `not_verified`. `segment=` for unlisted cars. Coverage level and disclaimer included. A merged key answers for its canonical fault |
| `GET /api/parts/{id}?variant_id=` | One part: prices, compatibility records, pictures, faults it is used for |
| `GET /api/parts/compare?ids=1,2&variant_id=` | Up to 6 parts side by side |

Safety tips about high-voltage / EV / hybrid parts are now shown only when the car's fuel is `ev` or `hybrid`
(red banner rules are unchanged and always run).

## Phase 3.2: repair estimates

`GET /api/estimates?session_id=&zone=&pincode=` gives, for each of the top 3 causes: parts, consumables, labour (with
service charges) and a total range rounded to the nearest Rs 50, every input with its source and check date, and
`flags.needs_check` when any input is older than 90 days, undated or unverified. A cause with no labour figure or no
usable part prices gets `status: "not_enough_data"` and the reasons, never a number.

- **One source of truth.** The result page's `cost` is built from the same estimate (same JSON shape as before), and so
  is the stored `session_results.cost_snapshot`. With no car-specific parts and no zone rate the estimate equals the
  sheet total within rounding (2,655 of the 2,658 sheet prices; F07-ST-29's sheet range adds 30% that its listed parts
  and labour do not explain). Costs code: `backend/app/estimates/` (`maths.py` has no database).
- **Parts.** The sheet's needed part lines (not "only if needed"), matched to approved catalogue rows. Parts listed for
  the customer's car (`part_compatibility`) give the min-max of their current prices; otherwise the line's segment
  price ("fit not verified"). If any line has no approved price (copied totals in file 7, quotations in file 6, rows
  under review), the sheet's own parts total, or total minus labour, is used and the reason is listed.
- **Labour.** Hours from the fault's repair time x the zone's hourly rate from `data/catalogue/zone_labour_rates.yaml`
  (empty until the team researches it; a rate needs a source and a date). Otherwise the sheet's labour, labelled
  "Delhi NCR metro estimate". Service lines (wheel alignment, scans, towing) count as labour, never as parts.
- **Zone.** `zone=` (delhi, noida, gurugram, ghaziabad, faridabad), else `pincode=`, else the pincode of a service
  request made from the session (`data/schema/zones.yaml`, reviewed: false); without one, the metro estimate is used and
  the response says so.
- **Parts review.** `uv run python -m app.parts review` then `autoreview` (first review by
  `claude_code (auto, pending mechanic sign-off)`, rules in `app/parts/autoreview.py`), then `build`. What a mechanic
  must check: `data/review/parts/REVIEW_NOTES.md`; lines never used as prices: `data/review/parts/excluded.csv`.
- `part_fit_verified` on the diagnosis result now comes from `part_compatibility` records for the car's variant
  (engine 1.4.0 / 2.3.0), not from words in the fit text.

## Phase 3.3: parts and estimates in the web app

- **Result page** (`/diagnose/{session}/result`): under the most likely cause, **Your area** (Delhi, Noida, Gurugram,
  Ghaziabad, Faridabad or a pincode) re-fetches `GET /api/estimates`; without a choice the label reads "Delhi NCR metro
  estimate". **Estimated cost** shows the total range, parts / labour / consumables, "Where these prices come from"
  (each input with its source and check date) and "The final price depends on the mechanic's inspection". A cause
  without enough data shows **Price on inspection** with Request a Mechanic. Because almost every estimate has
  `needs_check`, one calm line says "Prices are being verified with our mechanics". If `/api/estimates` cannot be
  reached, the result's own cost card is shown (the same numbers).
- **Parts you may need**: part cards (picture, name, brand type, price for the car's segment, "Fits your car" or
  "Fit not verified for your car"); tick 2 or 3 to compare. **`/parts/[id]`** shows one part (prices with dates, the
  models it is listed for, what it fixes); **`/parts/compare?ids=1,2,3`** compares up to 3 side by side. `variant_id`
  in the query decides the fit badge; without it no part is shown as fitting.
- Prices use Indian digit grouping (₹12,34,567) with tabular numbers. The result's `vehicle` now includes `variant_id`.
- Safety: the global smoke / fire rules no longer fire on the bare word "smoke" (black or white exhaust smoke is not a
  fire); smoke from the bonnet, wires, dashboard or cabin, in English, Hinglish or Hindi, still gives the high alert.

Try it: run the API and `pnpm dev` (see "Run"), finish a diagnosis for a listed car, then on the result pick an area,
open a part and compare two. Tests: `cd apps/web && pnpm test` and `pnpm test:e2e` (if Playwright times out with
parallel workers on a busy machine, use `pnpm exec playwright test --workers=1`).

## Phase 4.0: customer accounts

Anonymous diagnosis and requests work exactly as before; an account is optional.

- **Login by phone + OTP** (`/login`): Indian mobiles only (+91, 10 digits). `POST /api/auth/otp/request` sends a
  6-digit code (valid 5 minutes, 5 tries, one use; a new code replaces older ones); `POST /api/auth/otp/verify` needs
  the code and the ticked consent box (`GET /api/auth/config`; the consent version and time are stored on the user).
  Codes are stored as an HMAC with `AUTH_SECRET`, never in clear; phones in OTP rows only as an HMAC too. Limits: 3
  codes per phone per 15 minutes (in the database), 10 code requests and 20 checks per IP per window.
- **Cookies**: `im_session` (login, 30 days) is HttpOnly, Secure, SameSite=Lax and holds a random token whose SHA-256
  is in `auth_sessions`; logout revokes it. Anonymous visitors get an HttpOnly `im_anon` cookie when they start a
  diagnosis or send a request; logging in attaches the rows made with that cookie (only those: a session id alone
  never claims anything). CORS allows credentials for `WEB_ORIGIN` only.
- **`/account`**: My garage (catalogue cars you diagnosed, saved automatically), Diagnosis history, My requests,
  log out, and **Delete my account** (type DELETE): removes the phone, saved cars, logins, codes, diagnosis sessions
  with their answers and typed messages, typed-in unlisted cars, requests with their contact details and consent
  records, and `UPLOADS_DIR/<user id>` (no uploads exist yet). A count-only receipt stays in `account_deletions`.
- **`/requests/[id]`**: the status timeline (received → picked up → called → mechanic assigned → completed), read-only.
  Another customer's request answers 404.
- API: `GET /api/me`, `/api/me/vehicles` (`DELETE /api/me/vehicles/{id}`), `/api/me/sessions`, `/api/me/requests`,
  `GET /api/requests/{id}`, `POST /api/auth/logout`, `DELETE /api/me` (body `{"confirm": "DELETE"}`).
- Logs never contain a full phone number or a code (`+91******3210`), except the console SMS provider's own line.

### Try login locally (console SMS)

`SMS_PROVIDER=console` is the default. Start the API and the web app (see "Run"), open http://localhost:3000/login,
enter any valid mobile (e.g. 9876543210), press **Send code**, and read the code in the **API terminal**:

```
[console SMS] to +919876543210: Your Instant Mechanic login code is 482913. It expires in 5 minutes.
```

Type it, tick the consent box and press **Log in**. Diagnoses you made in that browser before logging in appear in
**My account**. Chrome and Firefox keep Secure cookies on http://localhost; if your browser does not, set
`COOKIE_SECURE=false` in `backend/.env` for local use only. The console provider is refused when
`ENVIRONMENT=production`, and the API refuses to start there without a real `AUTH_SECRET`.

### Going live with MSG91

`SMS_PROVIDER=msg91` is built (`backend/app/notify/sms.py`, MSG91 OTP API) but only starts when all three keys are set;
`.env.example` has empty placeholders. Before going live:

1. **MSG91 account** with KYC done and SMS credit; create an **auth key** (`MSG91_AUTH_KEY`), ideally restricted to
   the server's IP.
2. **DLT registration** (TRAI rules for commercial SMS in India), on a DLT portal (Jio, Vodafone Idea, Airtel, BSNL…):
   register the business as a **principal entity** (company documents, GST / PAN), then link the entity ID in MSG91.
3. **Sender ID (header)**: register a 6-letter header such as `IMECHN` on the DLT portal (`MSG91_SENDER_ID`).
4. **OTP template**: register a transactional/service-implicit template on DLT, e.g. "Your Instant Mechanic login code
   is {#var#}. It expires in 5 minutes. Do not share it.", then add it in MSG91 with the DLT template ID and use the
   MSG91 template ID as `MSG91_TEMPLATE_ID` (its variable is filled with the code).
5. Set `SMS_PROVIDER=msg91`, the three keys, `ENVIRONMENT=production`, a long random `AUTH_SECRET`, `COOKIE_SECURE=true`,
   serve the web app and API on one site (e.g. instantmechanic.online and api.instantmechanic.online) over HTTPS, and
   set `TRUST_FORWARDED_FOR=true` only behind your own proxy so the per-IP limits see real client addresses.
6. Send a test code to a team phone and check MSG91's delivery report.

## Phase 3.5: photo uploads

An optional **Add a photo** box sits under the questions in the chat. It never blocks the diagnosis: skip it, or
answer questions while it uploads; an error only affects the photo. Phones show **Take a photo** (back camera) and
**Choose from gallery**; desktops **Choose a photo**. You get a preview, retake / choose another, an upload progress
bar, plain error messages (wrong type, over 10 MB, upload failed, storage down) with **Try again**, and remove.

How it is kept safe:

- `POST /api/uploads` answers a **presigned POST** form for `incoming/<id>` in a **private bucket**; its signed policy
  limits the file to 10 MB, so the storage itself refuses bigger files. The browser posts straight to the storage.
- `POST /api/uploads/{id}/complete`: the API reads the file, decides its type from its **own bytes** (JPEG, PNG, WebP,
  HEIC; never the name or the declared type), refuses anything else, files over 10 MB and decompression bombs, turns
  the photo upright, resizes it to at most **2000 px**, and saves a **new JPEG with no metadata at all** (EXIF, GPS,
  XMP, ICC, comments) as `photos/<id>.jpg`. The raw upload is always deleted (a lifecycle rule also expires
  `incoming/` after a day).
- Only the **owner of the diagnosis session** (the logged-in customer, or the browser's anonymous cookie until login
  attaches it) can add, see, list or delete its photos; anyone else gets 404. `GET /api/uploads/{id}` answers a
  **signed link valid 5 minutes**; nothing is public. At most 5 photos per diagnosis; uploads are rate-limited per IP.
- **Account deletion** removes the photos from storage first; if the storage cannot be reached, nothing is deleted
  and the customer is asked to try again.
- Image analysis is not done yet: photos are stored for the mechanic.

### Local storage

MinIO no longer publishes free container images, so docker-compose runs **SeaweedFS** (Apache-2.0, S3-compatible)
as the `storage` service. The backend talks plain S3, so any S3 (AWS S3, Cloudflare R2, a MinIO you host) works in
production by changing the `S3_*` settings.

```bash
# backend/.env: your own local key pair (backend/.env.example has placeholders)
#   S3_ACCESS_KEY=...  S3_SECRET_KEY=...  S3_ENDPOINT_URL=http://localhost:8333  S3_PUBLIC_ENDPOINT_URL=http://localhost:8333
docker compose up -d storage                       # reads the key pair from backend/.env
cd backend && uv run python -m app.uploads.storage setup   # private bucket + 1-day expiry of incoming/
```

Try it: start a diagnosis at http://localhost:3000, and under the first question choose **Add a photo**. Tests:
`uv run pytest tests/test_uploads_imaging.py tests/test_uploads_api.py` (no storage needed) and
`tests/test_uploads_storage.py` (real presigned uploads against the local storage; skipped when it is not running).

In production, also set the bucket's CORS to allow `POST` from the web app's origin, and `S3_PUBLIC_ENDPOINT_URL` to
the address browsers use for the storage.

## Phase 3.6: photo analysis

After a photo is uploaded, the customer says whether it shows **a warning light on the dashboard** or **damage, wear
or a leak** (the default follows the problem), and `POST /api/uploads/{id}/analyze {"mode": "warning_light" | "damage"}`
reads it with a Claude vision model through the LLM layer (`backend/app/vision`).

- **Fixed list only.** The model may answer only codes from `image_labels` (18 warning lights with name, meaning,
  severity red / amber / info; 12 kinds of damage such as `belt_cracked`, `oil_leak`, `coolant_leak`, `tyre_worn`,
  `corrosion`), each with a confidence, or "unclear". Unknown codes are dropped; below `VISION_MIN_CONFIDENCE` it is
  "unclear, please retake from another angle". The list is seeded from the datasets
  (`data/review/image_labels.yaml` → `uv run python -m app.vision.catalogue seed`; re-run after a dataset import)
  and is `reviewed: false` until a mechanic checks it (`REVIEW_NOTES.md`).
- **Off by default, no cost.** With `LLM_PROVIDER=none` (or no `ANTHROPIC_API_KEY`) nothing is called: the answer is
  `unavailable` and the page says "A mechanic will look at your photo". A timeout, error, refusal or the daily spend
  cap gives `failed` with the same message. The photo is always kept for the mechanic, and nothing blocks the
  questions. The model sees only the re-encoded JPEG (no EXIF / GPS). A photo is read once per mode.
- **Results** are saved in `image_findings`. Customers see "Possible: …" with the meaning and "Photos can be
  misleading. A mechanic will check this before any repair."
- **Engine evidence.** Each label links to symptom lines of dataset faults; found labels add them to the engine
  request (`Request.photo_symptoms`) at a text score of 0.3, i.e. 0.9 after weighting, below the weakest answer
  weight (1). Safety rules are unchanged and still run on every call.
- **Safety.** A red warning light shows the red safety banner with the live safety rules of its faults (e.g. the
  red oil light: "Stop now and switch off the engine"); damage shows the banner for high-risk rules only (fuel or
  brake fluid leak, melted wiring).
- The customer's photos and findings also show on the results page and on `/requests/[id]`.

Try it without a key: upload a photo in the chat; it says "A mechanic will look at your photo". With a key
(`LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...` in `backend/.env`), photograph a dashboard light.

Evaluate on labelled photos (`data/eval/images/manifest.yaml`, format in `manifest.example.yaml`; empty for now):
`cd backend && uv run python ../data/eval/run_image_eval.py` reports correct / wrong / unclear rates per mode and
red-light recall (it calls Claude only with a key, and says so otherwise).

## Phase 4.1: staff access control

Staff sign in with **email + password + an authenticator code** (Google Authenticator or any TOTP app). Their login
is completely separate from customers' phone OTP login (own table, sessions and `im_staff` cookie). Roles:
`super_admin`, `content_admin`, `support_agent`, `mechanic` (and `customer`, every phone login, with no admin
access). Who may do what, and every rule, is in [docs/permissions.md](docs/permissions.md). Every admin write is
recorded in the append-only `audit_log`, with passwords, secrets, codes and phone numbers masked.

### Create your super admin (local)

1. Install Google Authenticator (or Microsoft Authenticator, 1Password, ...) on your phone. Make sure the phone's
   time is set automatically: codes depend on the clock.
2. Have the database and backend ready: `docker compose up -d db`, then
   `cd backend && uv sync && uv run alembic upgrade head` (staff tables: migrations 0015 and 0016).
3. `backend/.env` already has a local `STAFF_TOTP_KEY` (generated for you). On another machine, add one:
   `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and paste it
   as `STAFF_TOTP_KEY=...`. Keep it: changing it means setting up two-factor again.
4. Run, with your own email and name:
   ```bash
   uv run python -m app.admin.cli create-super-admin --email you@example.com --name "Your Name"
   ```
5. Type a password twice (at least 12 characters, not your email name; not shown on screen).
6. A QR code appears in the terminal, **only this once**. In Google Authenticator tap **+ > Scan a QR code** and scan
   it, or tap **+ > Enter a setup key** and type the key shown under it. Then type the 6-digit code the app shows:
   only then is the account saved.
7. Sign in at the admin app, http://localhost:3001 (see "Phase 4.2"), with the **next** code (a code works once).

Lost your phone, or want to set two-factor up again in the browser:
`uv run python -m app.admin.cli reset-two-factor --email you@example.com`. That removes two-factor; your next
sign-in at the admin app shows a new QR code and setup key once, then asks for a code. Locked out after 5 wrong
tries: wait 15 minutes, or `uv run python -m app.admin.cli unlock --email you@example.com`. The CLI refuses to
create a second "first" super admin (`--another` overrides it).

Tests: `uv run pytest tests/test_admin.py` (every admin endpoint with every role, login, two-factor setup, lockout,
sessions, cookies, audit masking and filters, customers, CORS, the CLI).

## Phase 4.2: admin app

`apps/admin`, a second Next.js app on **port 3001** next to the website on 3000, sharing `packages/ui` (`@im/ui`:
brand theme, Button, Dialog, data table). Start both with `pnpm dev` from the repo root (and the API on 8000).

- **Sign in** (`/login`): email and password, then the authenticator code. An account **without two-factor**
  (invited staff, or after a reset) gets the setup screen instead: the QR code and setup key, shown once, then a
  code from the app finishes it and signs in. Invited staff then must choose their own password before anything
  else. Sessions: 8 hours, 30 minutes idle.
- **Menu**: Overview, Requests, Mechanics, Knowledge, Vehicles, Parts & Prices, Datasets, Quality, Users, Audit log.
  Items are hidden by role (table in `docs/permissions.md`) and their pages say "No access" when opened directly;
  the API checks every call regardless (Datasets: Phase 4.3; Knowledge, Vehicles and Parts & Prices: Phase 4.4;
  Requests and Mechanics: Phase 4.5; Overview numbers and Quality: Phase 4.6).
- **Users**: the Staff tab (super admin) lists staff with search, role and status filters and CSV export, and lets
  you invite staff (a temporary password shown once), change roles, disable / enable, unlock and reset two-factor.
  The Customers tab (super admin, support agent) lists customer accounts with **masked phone numbers**; "Show"
  reveals one number for roles allowed to call customers, and every reveal is written to the audit log. The CSV
  never contains revealed numbers.
- **Audit log**: filters by action, entity, who and dates (India time), search, before/after JSON, CSV export.
- **Data table** (`@im/ui/data-table`, TanStack Table v8): search over all columns, select filters (array values
  such as roles match by "contains"), sorting, pagination, CSV export of every matching row (spreadsheet formulas
  neutralised). Later admin pages reuse it.

Tests: `cd apps/admin && pnpm test` (helpers) and `pnpm test:e2e` (Playwright, desktop + phone, API mocked: login
with two-factor, the setup screen, menus for each role, Users, Audit log); `cd packages/ui && pnpm test` (the table).

## Phase 4.3: dataset publish pipeline

The admin **Datasets** page (`content.read` to see it; super admins and content admins manage it) replaces the
manual steps after an import. Background jobs run in a worker (arq on Redis) and show their progress on the page.

- **Versions**: every dataset version is a complete copy of the knowledge, in one of four states: `draft`,
  `validated`, `published`, `archived`. Exactly one is published (the one the app serves), so every category has
  exactly one published version; publishing switches it in a single transaction (the old one is archived). The API
  picks up the new version without a restart, and a diagnosis in progress keeps the version it started on.
- **Upload** a category's Excel file (choose the file when a category has two, e.g. suspension). The draft is
  built from the live version's files with that one replaced, then every step runs automatically, in the order they
  were run by hand: questions load --all, merges apply, requirements apply, phrases load, safety_triggers apply,
  parts build, vision catalogue seed (checked for the draft, written at publish), embeddings sync. Embeddings are
  recomputed only for new or changed text: the rest reuse their stored vectors.
- **Validation report**: rows read / imported / rejected with reasons, and a **nothing lost** check against the
  live version (questions, answer effects, safety rules and trigger phrases, reviewed phrases, merges, requirements,
  parts links, photo labels, embeddings; unchanged categories must be identical). A draft with rejected rows or a
  loss stays `draft` and cannot be evaluated or published. A reviewed file that no longer matches (e.g. it names a
  removed fault) fails the build with the step's name.
- **Diff** against the live version: added, changed (with the fields, before and after) and removed fault rows.
- **Eval** in the background: by default the test split of the categories the upload changes (a few minutes), or
  the full run (optional, slow). The live version runs on the same cases and the page compares them.
- **Publish** is blocked when top-3 accuracy drops by more than 3 points or safety recall drops at all, measured on
  the cases both versions have (matched by fault keys and question / answer text, not database ids), or when a danger
  case of the live version is missing from the draft. Safety recall is shown as "N of M danger cases missed (98.86%)",
  with the safety cases whose outcome changed and the cases only one version has. A super
  admin can override with a written reason (at least 15 characters), saved on the version and in the audit log
  (`dataset.publish_override`). Publishing runs the steps once more, checks nothing is lost, then switches.
- **Discard** a draft; **Rebuild** a draft that was built before another category was published.
- **Roll back** from any archived version: choose a category and confirm. A new version is built from the live
  files with that category's file as it was then, checked and published; other categories keep their data.

```bash
docker compose up -d db storage redis
cd backend && uv run alembic upgrade head            # migration 0017
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd backend && uv run arq app.datasets.worker.WorkerSettings
pnpm dev:admin                                       # http://localhost:3001/datasets
```

Then on the Datasets page: publish the imported version once (it has no history yet), upload a category file, open
the draft, run the evaluation, publish (or override), and try a rollback from the History table. Uploaded files are
kept in `data/uploads/datasets/` (not committed). A job that waits for a long time means the worker is not running;
a job left running by a stopped worker is marked failed when the worker starts again.

Tests: `cd backend && uv run pytest tests/test_datasets.py` (the whole lifecycle with fixture files: blocked publish,
override, nothing lost, changed-only embeddings, stale draft, discard, rollback, worker failures) and
`cd apps/admin && pnpm exec playwright test e2e/datasets.spec.ts --workers=1`.

## Phase 4.4 (part 1): knowledge editors and review queues

The admin **Knowledge** page edits the knowledge in a **draft**, never live: changes are published through the
dataset pipeline (Datasets page: evaluation, gate, publish). Super admins and content admins edit (`knowledge.edit`);
support agents and mechanics cannot.

- **Drafts**: "Start an edit draft" copies the live version (about a minute and a half in the worker). Uploaded drafts
  can be edited too. The bar at the top shows which draft you are editing.
- **Faults**: details, applicability (what the car must have), weight (engine v2 prior), symptoms, causes, diagnostic
  steps, repair steps, advice, safety precautions, towing, mechanic lines (internal), synonyms (Hinglish, English or
  Hindi in Devanagari), pictures (from the dataset files) and safety rules; new faults get the next key of their
  category's file.
- **Questions**: text, stage, answers and their effects on faults (supports / rules out, strong / moderate / weak:
  the weights the engine uses).
- **Tiles & categories**: problem tiles, the emergency row, the inspection booking, categories (kind, Beta, wave,
  vehicle filters, engine settings) and vehicle filters. This replaces editing data/schema/taxonomy.yaml.
- **Safety rules**: every change shows a warning, needs a confirmation and is audited with its old and new values
  (`knowledge.safety_edit`). Rules are never deleted (status rejected).
- **Sign-off**: items checked automatically ("claude_code (auto, pending mechanic sign-off)": questions, reviewed
  phrases, safety rules and triggers, photo labels) with a filter for those still pending; "Sign off as me" records
  your name and today's date (a safety rule becomes approved).
- **Changes in this draft**: every edit with its old and new values and a revert. The publish page (Datasets, the
  version) shows the same: counts per table, every safety change by name, conflicts and edits not applied.
- **Surviving a re-import**: edits are overrides on top of the imported data (`knowledge_edits`), re-applied as a
  pipeline step after every import. If a new Excel file changes a field you edited, your edit is kept and the draft
  lists it as a conflict; if the file removes the item, the edit is listed as not applied.
- **Review queues** (Knowledge → proposed questions and sign-off): questions proposed by the LLM (edit and approve
  into the draft, or reject; empty while no LLM API is configured) and the questions waiting for sign-off. **Vehicles**:
  cars customers typed because they were not listed: add to the catalogue (live at once, audited; `vehicles.seed`
  never deletes them unless run with `--prune`) or dismiss.

```bash
cd backend && uv run alembic upgrade head            # migration 0018
# restart the worker (it runs the new "editor edits apply" step) and the API
cd backend && uv run arq app.datasets.worker.WorkerSettings
cd backend && uv run uvicorn app.main:app --reload --port 8000
pnpm dev:admin                                       # http://localhost:3001/knowledge
```

Tests: `cd backend && uv run pytest tests/test_knowledge_editors.py`; `cd apps/admin && pnpm test` and
`pnpm exec playwright test e2e/knowledge.spec.ts --workers=1`.

## Phase 4.4 (part 2): vehicles, parts & prices, pictures, bulk sign-off

- **Vehicles** (catalogue tab): makes, models, generations and variants (price segment, years, features). The car
  catalogue is not part of the dataset versions: a change is live at once for new diagnoses and audited. Rows changed
  here are marked: `python -m app.vehicles.seed` keeps them as they are (and never prunes them) and lists them. A
  variant that diagnoses or saved cars use cannot be deleted.
- **Parts & Prices** (edits in a draft, published on the Datasets page; a new pipeline step re-applies them after
  `parts build`, so every rebuild keeps them):
  - Parts (new ones are created at once; a change to an existing part reaches the shared parts list at publish),
    pictures, fits (which cars a part fits) and prices.
  - Every price needs a **source** (supplier or link) and the **date it was checked**. A price of **₹20,000 or more is
    flagged** until a second person checks it ("Second look"; never the person who entered it); the publish page lists
    the ones waiting (they do not block publishing).
  - **Labour rates**: the zone grid (per hour, zone × segment, with source and date) fills the version's zone rates:
    estimates use them once published. `data/catalogue/zone_labour_rates.yaml` is loaded on every build; "Download as
    zone_labour_rates.yaml" gives the file to commit. Plus the per-repair labour research rows.
  - **CSV import**: download the template, check the file (errors and flags per row, nothing saved), then import the
    valid rows into the draft (one audit entry).
- **Pictures** for faults and parts are uploaded through the photo storage (SeaweedFS, the same checks as customer
  photos: real type, re-encoded JPEG, no metadata) and served at `/media/uploaded/<sha1>.jpg`.
- **Bulk sign-off**: on the Sign-off tab, "Sign off all N shown" signs off everything the current search and filters
  show (up to 2,000 at a time) as one audit entry with the count and the filter.

```bash
cd backend && uv run alembic upgrade head            # migration 0019
docker compose up -d storage                         # pictures (S3 key pair in backend/.env, as for photos)
# restart the worker (new pipeline steps) and the API
pnpm dev:admin                                       # http://localhost:3001/vehicles and /parts
```

Tests: `cd backend && uv run pytest tests/test_parts_editors.py`; `cd apps/admin && pnpm exec playwright test
e2e/parts.spec.ts --workers=1`.

## Phase 4.5 (part 1): mechanics and the request workflow (API)

- **Request statuses**: submitted → triaged → offered → accepted → en_route → arrived → in_progress → completed, plus
  cancelled and escalated. Only the moves in `backend/app/requests/workflow.py` are allowed; every change writes a
  `request_events` row and an audit entry. Offers, the mechanic's answer and completion have their own actions.
- **Support queue** `GET /api/admin/requests`: safety-critical first (the diagnosis's red banner = `safety_level`
  high), then urgent, then the oldest. Customer phone numbers are always masked; only the agent who owns the request
  (the one who triaged or took it) can reveal the number, and each reveal is audited.
- **Matching** `GET /api/admin/requests/{id}/suggestions`: on duty and in a shift (India time), works the area
  (pincode or radius), has the skill (the request's category), not full today; ranked by distance 45 %, rating 25 %,
  acceptance rate 20 %, jobs today 10 %, with reasons for each suggestion and for each mechanic left out.
  Suggestions only: an agent offers the job (no auto-assign, no notifications).
- **Distances** come from `data/schema/pincode_centres.yaml`: pincode centre points from GeoNames (CC BY 4.0, no paid
  API). About half the NCR pincodes only have rough points; the suggestions say so.
- **Completing a job** records the confirmed fault (or "other" with a description), whether it was the AI's top 1 /
  in the top 3, parts used, final cost, mechanic notes and the diagnosis's dataset version (`request_outcomes`).
- **Mechanics API** `/api/admin/mechanics`: create, edit, skills, zones, shifts, on / off duty. **Documents** are
  encrypted with `MECHANIC_DOCS_KEY` (super admins only; every view audited). Without the key, uploads are refused.
- **Customer page** `/requests/[id]`: plain words ("Mechanic on the way"), the steps with India times, the status
  changes, and the mechanic's first name once one took the job (never a phone number or documents).
- The admin pages (Mechanics with the map, Requests queue and detail) are part 2 (below).

```bash
cd backend && uv run alembic upgrade head            # migration 0020
uv run python -m app.mechanics.dev_seed              # 5 fake mechanics, development only (--remove deletes them)
# restart the API; add MECHANIC_DOCS_KEY to backend/.env for documents (see .env.example)
```

Tests: `cd backend && uv run pytest tests/test_mechanics.py`.

## Phase 4.5 (part 2): Requests and Mechanics pages (admin app)

- **Requests** (`/requests`, `requests.read`): the queue in the API's order (safety-critical with a red badge, then
  urgent, then the oldest), how long each has waited, masked phone numbers. Filters: open / closed / all, status,
  safety, category, "only mine" and search (reference, name, area, pincode); they are kept in the page address.
- **Request page** (`/requests/[id]`): the customer (phone masked; "Show number" only for the agent who owns the
  request, audited; "Take this request" to own it), the car and the AI's top causes, a map of the pincode's centre
  (**"rough location"** when the pincode only has an estimated point, "area centre only" for a zone centre), the
  suggested mechanics with their reasons (and who was left out and why), offer a job (someone who is not a
  suggestion needs a note), the mechanic's answer, the status buttons (cancel / escalate need a note), internal
  notes, the timeline and, for a job in progress, the **complete-job form**: the confirmed fault (the AI's top 3
  first, then the category's faults, or "Other" with a description), parts used, final cost and the mechanic's notes.
- **Mechanics** (`/mechanics`, `mechanics.read`; editing `mechanics.manage`): the list with an on / off duty switch
  and a map of their bases; add a mechanic; each mechanic's details, skills (categories), zones (pincodes or a radius
  around the base or a point clicked on the map) on the map, weekly shifts (India time; overlaps refused) and, for
  super admins only, **documents** (upload, view, delete; encrypted and audited by the API).
- **Maps**: Leaflet with OpenStreetMap tiles, **for development only**. OSM's public tiles are not for production
  traffic: set `NEXT_PUBLIC_MAP_TILE_URL` (and `NEXT_PUBLIC_MAP_ATTRIBUTION`) in `apps/admin/.env.local` to a proper
  tile provider before going live. Every point on a map is also written out as text.
- API additions: `GET /api/admin/requests/{id}/faults` (the complete-job choices) and the precision of mechanics'
  base and zone points (`base_precision`, `zones[].precision`).

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000   # restart the API (new endpoint)
uv run python -m app.mechanics.dev_seed                          # optional: 5 fake mechanics
pnpm dev:admin                                                   # http://localhost:3001/requests and /mechanics
```

Tests: `cd backend && uv run pytest tests/test_mechanics.py`; `cd apps/admin && pnpm test` and
`pnpm exec playwright test e2e/requests.spec.ts e2e/mechanics.spec.ts --workers=1`.

## Phase 4.6: Overview and Quality pages

Staff guide in plain English: [docs/admin-guide.md](docs/admin-guide.md) (daily startup, requests, completing a job,
editing knowledge, publishing and rolling back, sign-off, Quality).

- **Overview** (`GET /api/admin/overview`; every staff member, parts by permission): today in India time. Requests
  today by status and those with **no agent after 10 minutes** (safety-critical ones in red), for `requests.read`;
  diagnoses today, safety alerts today and **LLM spend today**, for `quality.read`.
- **Quality** (`quality.read`: super admins, content admins; last 7 / 30 / 90 days):
  - Safety: danger cases missed in the latest evaluation, safety alerts shown today.
  - The latest evaluation of the live dataset version (the Datasets page's eval): accuracy by category; **real cases
    in their own table**, never mixed in.
  - Confirmed-outcome accuracy (`request_outcomes`: the engine's top-1 / top-3 against the mechanic's confirmed fault),
    by category and by dataset version, with case counts; **"not enough data yet" under 30 cases**.
  - Low-confidence rate, no-match rate, average questions answered (undone answers not counted), helpful rate.
  - LLM failures and fallback rate. With no live LLM (`LLM_PROVIDER=none`, or no key) every LLM figure says
    **"LLM off"**, never zeros.
  - Review lists: negative feedback, low-confidence and no-match sessions. Each opens a **read-only replay** (every
    question and answer with its time; taken-back answers marked; phone numbers, emails and plates masked).
- **Golden set** (`quality.golden`): "Add to golden set" on a replay writes one real case to
  `data/eval/golden/real_cases/` (`source: real`; names, phones, plates, addresses and house numbers removed; pincode
  and zone only) and records it in `golden_cases` (migration 0021; once per session; audited). The eval harness and
  the Datasets evaluation run real cases and report them **apart** (report `summary.real`, eval `real`); they never
  count in the main numbers or the publish gate. Format, and how the old platform's job records can be added later:
  [data/eval/golden/README.md](data/eval/golden/README.md).
- New permissions `quality.read`, `quality.golden` (super admin, content admin); Quality moved from `content.read`.
  New setting `GOLDEN_CASES_DIR` (default `data/eval/golden/real_cases`).

```bash
cd backend && uv run alembic upgrade head            # migration 0021
# restart the API and the worker (the worker now evaluates real cases too)
pnpm dev:admin                                       # http://localhost:3001 (Overview) and /quality
```

Tests: `cd backend && uv run pytest tests/test_quality.py tests/test_eval_harness.py`; `cd apps/admin && pnpm test`
and `pnpm exec playwright test e2e/quality.spec.ts --workers=1`.

## Phase 5.1: containers and production

Production images for the four apps, and two compose files. Local development is unchanged: keep running the
API, the worker and `pnpm dev` on your machine (Phase 1 run guide), with `docker compose up -d db storage redis`.

| File | What |
|---|---|
| `backend/Dockerfile` | API **and** worker image (same image, different command). Multi-stage, uv, **CPU-only torch** (Linux wheels from the PyTorch CPU index, set in `pyproject.toml`; macOS keeps its wheel), the embedding model `EMBEDDING_MODEL` downloaded at **build** time and used offline (`HF_HUB_OFFLINE=1`), non-root user `app` (uid 10001). Target `dev` adds the dev group for hot reload |
| `apps/Dockerfile` | Web **or** admin image (`--build-arg APP=web\|admin`): pnpm workspace, Next.js `output: "standalone"` (only when `NEXT_OUTPUT=standalone`, which the image sets: local `next start` and Playwright are unchanged), runs as the non-root `node` user. `NEXT_PUBLIC_*` are **build args** |
| `docker-compose.yml` | Development: `db`, `storage` (SeaweedFS), `redis` as before; `api`, `worker`, `web`, `admin` with hot reload under the `app` profile |
| `docker-compose.prod.yml` | Production, project `autocare-prod` with its **own volumes** (`pgdata_prod`, …): `caddy`, `web`, `admin`, `api`, `worker`, `db` (pgvector), `redis`, one-off `migrate`; `storage` (SeaweedFS) under the `storage` profile; one-off `setup` and `tools` |
| `docker-compose.prod.local.yml` | Only for the local production test: publishes Caddy's extra localhost ports (see below) |
| `docker/caddy/Caddyfile` | Reverse proxy with automatic HTTPS |
| `.env.prod.example`, `backend/.env.prod.example` | Placeholders. The real `.env.prod` and `backend/.env.prod` are git-ignored |

**Domains.** `instantmechanic.online` → web, `admin.instantmechanic.online` → admin, **`api.instantmechanic.online`**
→ API, `files.instantmechanic.online` → photo storage. The API gets its own subdomain rather than `/api` on the main
domain because: the API also serves `/media`, `/docs` and `/openapi.json`, which would have to be carved out of the
web app's paths on one host; the admin app calls the API from another origin either way, so CORS is needed regardless; and it is exactly the
setup development already uses (two app origins calling a separate API origin, CORS `WEB_ORIGIN` / `ADMIN_ORIGIN`),
so cookies and CORS behave the same as on localhost. All three are subdomains of one site, so the SameSite customer
and staff cookies still work. The cost is one more DNS record and certificate. Photos get their own host too
(`files.`): presigned links are signed for the host and path the browser uses, which a path prefix would break.

**Images.** API / worker: about 3.0 GB on disk, 0.9 GB to download (CPU torch is 650 MB of it, the model 460 MB;
the default Linux torch would add several GB of CUDA libraries). Web and admin: about 300 MB each, 75 MB to download. Not in any image: `data/raw` (the 18 Excel files), `data/media` (their pictures),
`data/uploads`, `data/models` and `.env` files; compose mounts them. The model is loaded once per process (API: the
first free-text search; worker: the first job that embeds).

### Run the production stack locally

Caddy serves the stack on `https://localhost` with its own CA (`CADDY_TLS=internal`, `HSTS_MAX_AGE=0`). Locally the
admin app, the API and the photo storage are **ports** of localhost (`:8444`, `:8443`, `:8445`) instead of
subdomains: `localhost` has no registrable domain, so `api.localhost` would be a different *site* from `localhost` and
browsers would withhold the API's SameSite cookies (anonymous diagnosis, login, photos). Ports do not change the site,
so this behaves like `instantmechanic.online` and its subdomains in production. The extra ports are published by
`docker-compose.prod.local.yml`, used only here. Ports 80, 443 and 8443-8445 must be free. The stack uses about
1.5 GB of RAM in Docker once the model is loaded (the one-off import about 1.5 GB more); on an 8 GB Mac build one image at a time.

```bash
cp .env.prod.example .env.prod                 # set: WEB_DOMAIN=localhost API_DOMAIN=localhost:8443
                                               #      ADMIN_DOMAIN=localhost:8444 FILES_DOMAIN=localhost:8445
                                               #      CADDY_TLS=internal HSTS_MAX_AGE=0 and a POSTGRES_PASSWORD
cp backend/.env.prod.example backend/.env.prod # set: WEB_ORIGIN=https://localhost ADMIN_ORIGIN=https://localhost:8444
                                               #      S3_PUBLIC_ENDPOINT_URL=https://localhost:8445 EMAIL_PROVIDER=console,
                                               #      new AUTH_SECRET, STAFF_TOTP_KEY, MECHANIC_DOCS_KEY, S3 key pair
# bash / zsh helper (on a real server leave out the docker-compose.prod.local.yml part)
dcp() { docker compose -f docker-compose.prod.yml -f docker-compose.prod.local.yml --env-file .env.prod "$@"; }

dcp build api                                  # one at a time (8 GB machines): api, then web, then admin
dcp build web
dcp build admin
dcp --profile storage up -d                    # migrate runs first; api and worker wait for it
dcp --profile storage ps                       # all "healthy"; migrate "exited (0)"
dcp --profile storage --profile setup run --rm setup   # once: photo bucket and vehicle seed
```

Then load the data with the commands of step 5 below (about 10 minutes, mostly embeddings on CPU), and open
https://localhost (admin: https://localhost:8444, API docs: https://localhost:8443/docs). The browser warns about
the certificate once per port; to trust Caddy's CA instead (macOS):
`docker compose -p autocare-prod cp caddy:/data/caddy/pki/authorities/local/root.crt caddy-root.crt`, open it and
mark it trusted in Keychain Access. The login code of the console SMS provider is refused in production mode, so
customer login is not available locally unless MSG91 is configured.

Stop with `dcp --profile storage down` (add `-v` to delete the production volumes; the development database is a
different volume of a different project and is never touched).

### Fresh server

1. A Linux server with Docker (Compose 2.24+), 2 vCPU / 4 GB RAM or more. DNS A (and AAAA) records for the four
   hosts point at it; ports 80 and 443 open.
2. Clone the repo. Copy the 18 Excel files to `data/raw/` (or set `DATA_RAW_DIR`), and give the app user the
   pictures folder: `mkdir -p data/media && sudo chown -R 10001:10001 data/media`.
3. `cp .env.prod.example .env.prod` and `cp backend/.env.prod.example backend/.env.prod`; replace every
   placeholder (the comments say how to generate each secret). `CADDY_TLS` is your email for certificate notices.
   Single server: keep the `storage` profile and `S3_ENDPOINT_URL=http://storage:8333`,
   `S3_PUBLIC_ENDPOINT_URL=https://files.<domain>`. Cloud bucket: point the `S3_*` settings at it and leave the
   `storage` profile off (Caddy's `files.` host is then unused).
4. Build and start (as above, without the localhost values): `dcp build api && dcp build web && dcp build admin`,
   then `dcp --profile storage up -d`.
5. One-off setup and data import, in this order (each `run --rm` starts a container from the API image and exits):

```bash
dcp --profile storage --profile setup run --rm setup                     # bucket + CORS + lifecycle, vehicle seed
dcp run --rm tools python -m app.knowledge.importer --all               # the 18 datasets (+ pictures into data/media)
dcp run --rm tools python -m app.knowledge.questions load --all
dcp run --rm tools python -m app.knowledge.merges apply
dcp run --rm tools python -m app.knowledge.requirements apply
dcp run --rm tools python -m app.knowledge.phrases load
dcp run --rm tools python -m app.knowledge.safety_triggers apply
dcp run --rm tools python -m app.vision.catalogue seed
dcp run --rm tools python -m app.knowledge.embeddings sync
dcp run --rm tools python -m app.parts build
dcp restart api                                                           # loads the new safety rules
dcp run --rm tools python -m app.admin.cli create-super-admin --email you@example.com --name "Your Name"
```

6. Sign in at `https://admin.<domain>`, open **Datasets** and **publish** the imported version once (Phase 4.3). From
   then on category files are uploaded there and the worker runs every step. The importer's review outputs
   (`data/review/…`) are written inside the one-off container; the reviewed files themselves are part of the image,
   so a change to them ships with a rebuild.

Updating: `git pull`, rebuild the images (one at a time), `dcp --profile storage up -d` (migrations run first). A
change to `NEXT_PUBLIC_*`, the domains or `EMBEDDING_MODEL` needs a rebuild of the image that bakes it in.

### Development in containers (optional)

```bash
docker compose --profile app up --build        # db, storage, redis + api :8000, worker, web :3000, admin :3001
```

Same ports as the host processes, so stop those first. The API and the worker read `backend/.env` (the database,
Redis and storage addresses are switched to the containers); the web apps read their `.env.local`. Code changes
reload the API (uvicorn `--reload`), the worker (`arq --watch`) and both apps (`next dev`). `node_modules` for Linux
and the downloaded model live in named volumes, so the host's macOS `node_modules` and `.venv` are untouched.

### Tests

```bash
cd backend && uv run pytest tests/test_deploy_config.py tests/test_uploads_setup.py   # compose / Dockerfile rules,
                                                                                      # bucket CORS
# Smoke test of the running local production stack through Caddy (after the data import; Caddy's certificates are
# accepted in this mode): API health and CORS, a real diagnosis start with a photo upload to the storage and back,
# the admin sign-in page and its headers, the storage's CORS for the web origin and not for others.
cd apps/web && E2E_BASE_URL=https://localhost E2E_API_URL=https://localhost:8443 E2E_ADMIN_URL=https://localhost:8444 \
  E2E_FILES_URL=https://localhost:8445 pnpm exec playwright test e2e/prod-smoke.spec.ts --workers=1
```

`E2E_BASE_URL` makes the web Playwright config test a running deployment instead of building and starting its own
server; without it every suite runs as before.

## LLM layer (off by default)

`backend/app/llm` adds two optional steps, each with a non-LLM fallback. The engine always decides which question
to ask, ranks the faults and runs every safety rule; prices, part fit and safety rules come only from the database.

| Step | With the LLM | Fallback (and with `LLM_PROVIDER=none`) |
|---|---|---|
| Extraction (session text and `POST /api/diagnosis/sessions/{id}/messages`) | The message plus up to 60 candidate symptom lines (with ids) and the waiting question go to Claude as one strict tool call; it returns symptom ids and maybe an answer. Ids not offered and options not offered are dropped. | Engine v2 + hybrid search match the words, as before |
| Phrasing (each question in a session where the customer typed something) | The chosen question is reworded in the customer's language (English, Hindi or Hinglish); no numbers, prices, links or markup allowed | The original question text |
| Explanation (result page, streamed) | Two or three plain sentences per cause from the facts the engine found; dropped per cause if it names another fault, a price, a number or a part not in the facts | Template explanations |

How it is kept safe and cheap:

- Phones, emails and number plates are masked before anything is sent (`app/llm/mask.py`). Customer text sits
  inside `<customer_message>` (escaped) in the user turn, never in the system prompt; the prompt says it is data.
- About 4 s per call (`LLM_TIMEOUT_SECONDS`), no retries; on timeout, refusal, invalid output or an API error the
  fallback is used and the session carries on.
- `LLM_DAILY_SPEND_CAP_USD` (estimated, India-time day): once reached, no calls until midnight.
- Every call is logged in `llm_calls` (purpose, model, prompt version, tokens, latency, estimated cost, outcome:
  `ok`, `dropped`, `invalid`, `refused`, `timeout`, `error`, `spend_cap`). The customer's text is never logged there.
- Prompts are versioned files in `backend/app/llm/prompts/` (`extraction.v1.md`, `phrasing.v1.md`); to change one,
  add `*.v2.md` and point `VERSIONS` in `prompts/__init__.py` at it.

### Free-text turns

`POST /api/diagnosis/sessions/{id}/messages` with `{"text": "..."}` (1-1000 characters). The words join the
session's description (so safety words fire alerts at once). If they answer the waiting question, it is recorded
as the answer; otherwise that question is set aside (`question_withdrawn` event) and the engine picks the next one
again. The response is like an answer's, plus `understood: {source: llm|fallback, symptoms, answered_question}`.
Questions carry `phrased: true` when the text was reworded.

```bash
curl -s -X POST localhost:8000/api/diagnosis/sessions/<session id>/messages \
  -H 'Content-Type: application/json' -d '{"text": "battery se tik tik awaaz aati hai"}'
```

### Switching it on later

1. Get a Claude API key and put it in `backend/.env` (never in `.env.example` or git):
   `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=sk-ant-...`.
2. Optionally set `LLM_DAILY_SPEND_CAP_USD` (default 2) and the models (default `claude-haiku-5-5`; a model must
   have a price in `backend/app/llm/pricing.py` or it is never called).
3. Restart the API. Check calls with
   `docker compose exec db psql -U autocare -d autocare -c "select created_at, purpose, model, outcome, input_tokens, output_tokens, latency_ms, cost_usd from llm_calls order by id desc limit 20;"`
   and today's spend with `select sum(cost_usd) from llm_calls where created_at >= date_trunc('day', now() at time zone 'Asia/Kolkata') at time zone 'Asia/Kolkata';`.
4. Measure extraction before relying on it: `cd backend && uv run python ../data/eval/run_eval.py run --split test
   --extraction llm --label llm-extraction`, then `compare` against the `--extraction none` report. The report shows
   the calls, outcomes, tokens and estimated cost. `EXTRACTED_SYMPTOM_SCORE` in `engine/core.py` (0.8) is not tuned
   yet: tune it on `--split dev`.

To switch it off again, set `LLM_PROVIDER=none` (or empty the key) and restart.

## Troubleshooting

- **Web page shows "We couldn't reach our server"**: the API is not running on port 8000, or the web app is not on
  `WEB_ORIGIN` (default `http://localhost:3000`).
- **Next.js dev overlay error "Could not validate `instant`" after installing packages**: restart `pnpm dev`.
- **429 Too many requests**: the per-IP limits (`SESSION_RATE_LIMIT`, `REQUEST_RATE_LIMIT`); restart the API to reset.
- **No helpline on the request page / `alert_error = SUPPORT_EMAIL is not set`**: set `HELPLINE_NUMBER` and
  `SUPPORT_EMAIL` in `backend/.env` and restart the API.
- **First diagnosis after starting the API takes ~10 s**: hybrid search loads the embedding model once. Set
  `DIAGNOSIS_SEARCH=keyword` to skip it. After importing data, run `python -m app.knowledge.embeddings sync`.
- **Playwright fails on every test**: another server is already on port 3100 (it is reused); stop it.
