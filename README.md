# Instant Mechanic: AI car diagnosis

AI car diagnosis chatbot and mechanic assistance platform for [Instant Mechanic](https://instantmechanic.online), Delhi NCR. Project rules are in [CLAUDE.md](CLAUDE.md).

## Layout

| Path | What |
|---|---|
| `apps/web` | Customer site (port 3000): Next.js (App Router), TypeScript, Tailwind CSS v4, shadcn/ui |
| `apps/admin` | Staff admin app (port 3001): sign-in with two-factor, role-based menu, Users, Audit log |
| `packages/ui` | `@im/ui`, shared by both apps: brand theme, Button, Dialog, the data table (TanStack Table) |
| `backend/app` | FastAPI app. Modules: `vehicles`, `knowledge`, `diagnosis`, `requests`, `accounts` (phone + OTP login), `uploads` (customer photos), `notify` (email and SMS), `llm` (optional LLM layer, off by default), `parts` (parts catalogue) |
| `backend/engine` | Diagnosis engine, plain Python with no web imports |
| `backend/alembic` | Database migrations |
| `data/raw` | The 18 original Excel datasets. Never edit |
| `data/schema` | Manifest, column aliases, taxonomy, import rules, CSV templates for price sources (`templates/`) |
| `data/catalogue` | Vehicle catalogue seed (editable YAML); team price sources in `parts/` |
| `docs` | Dataset profile, findings, data model, [how the engine and LLM layer work](docs/diagnosis-engine.md), [adding a category](docs/adding-a-category.md) |
| `scripts` | Offline data scripts (dataset profiler) |
| `docker-compose.yml` | PostgreSQL 16 + pgvector, and S3-compatible storage for photos (SeaweedFS) |

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

# Database: PostgreSQL 16 + pgvector, plus an autocare_test database for pytest; photo storage (S3, SeaweedFS)
docker compose up -d db storage

# Backend and data (run in this order)
cd backend
uv sync
uv run alembic upgrade head                          # all migrations (0001 … 0016)
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

# Web apps (one pnpm workspace at the repo root: apps/web, apps/admin, packages/ui)
pnpm install                                          # from the repo root
pnpm --filter web exec playwright install chromium    # once, for the end-to-end tests
```

After pulling new code, run `uv run alembic upgrade head` again, and restart `pnpm dev` after any `pnpm install`.

### 2. Run

Two terminals: the API, then both web apps together.

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
# http://localhost:8000/api/health  ->  {"status":"ok","database":"ok"}
# http://localhost:8000/docs        ->  API docs with request and response schemas
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
  the API checks every call regardless. Requests, Mechanics, Knowledge, Vehicles, Parts & Prices, Datasets and
  Quality are placeholders for now.
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
