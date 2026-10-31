# Instant Mechanic: AI car diagnosis

AI car diagnosis chatbot and mechanic assistance platform for [Instant Mechanic](https://instantmechanic.online), Delhi NCR. Project rules are in [CLAUDE.md](CLAUDE.md).

## Layout

| Path | What |
|---|---|
| `apps/web` | Customer site: Next.js (App Router), TypeScript, Tailwind CSS v4, shadcn/ui |
| `backend/app` | FastAPI app. Modules: `vehicles`, `knowledge`, `diagnosis`, `requests`, `notify` (email alerts), `llm` (optional LLM layer, off by default), `parts` (parts catalogue) |
| `backend/engine` | Diagnosis engine, plain Python with no web imports |
| `backend/alembic` | Database migrations |
| `data/raw` | The 18 original Excel datasets. Never edit |
| `data/schema` | Manifest, column aliases, taxonomy, import rules, CSV templates for price sources (`templates/`) |
| `data/catalogue` | Vehicle catalogue seed (editable YAML); team price sources in `parts/` |
| `docs` | Dataset profile, findings, data model, [how the engine and LLM layer work](docs/diagnosis-engine.md), [adding a category](docs/adding-a-category.md) |
| `scripts` | Offline data scripts (dataset profiler) |
| `docker-compose.yml` | PostgreSQL 16 + pgvector |

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

# Database: PostgreSQL 16 + pgvector, plus an autocare_test database for pytest
docker compose up -d db

# Backend and data (run in this order)
cd backend
uv sync
uv run alembic upgrade head                          # all migrations (0001 … 0011)
uv run python -m app.vehicles.seed                   # vehicle catalogue from data/catalogue/vehicles.yaml
uv run python -m app.knowledge.importer --all        # the 18 datasets (first run downloads a ~470 MB model)
uv run python -m app.knowledge.questions load --all  # approved question flows + safety rules (data/review/questions)
uv run python -m app.knowledge.merges apply          # approved duplicate-fault merges (data/review/merges.yaml)
uv run python -m app.knowledge.requirements apply    # what faults need (start-stop, diesel, AMT …): data/review/fault_requirements.yaml
uv run python -m app.knowledge.phrases load          # reviewed extra customer phrases (spellings, Hindi): data/review/phrases
uv run python -m app.knowledge.safety_triggers apply # reviewed phrases for global emergency rules: data/review/safety_global_triggers.yaml
uv run python -m app.knowledge.embeddings sync       # search index: embeds only new or changed texts
uv run python -m app.parts build                     # parts catalogue (after merges): prices, fits, fault links, labour
cd ..

# Web
cd apps/web
pnpm install
pnpm exec playwright install chromium                # once, for the end-to-end tests
cd ../..
```

After pulling new code, run `uv run alembic upgrade head` again, and restart `pnpm dev` after any `pnpm install`.

### 2. Run

Two terminals:

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
# http://localhost:8000/api/health  ->  {"status":"ok","database":"ok"}
# http://localhost:8000/docs        ->  API docs with request and response schemas
```

```bash
cd apps/web && pnpm dev
# http://localhost:3000   (use port 3000: the API's CORS allows only WEB_ORIGIN)
```

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
cd apps/web && pnpm test                     # Vitest component tests
cd apps/web && pnpm test:e2e                 # Playwright, phone + desktop (builds and serves the app on :3100;
                                             # the API is mocked, no backend needed)
# Optional: the same flows against the real API and database, LLM off (own ports, so `pnpm dev` keeps working):
cd backend && LLM_PROVIDER=none WEB_ORIGIN=http://localhost:3110 uv run uvicorn app.main:app --port 8010
cd apps/web && E2E_LIVE_API=1 E2E_PORT=3110 NEXT_PUBLIC_API_URL=http://localhost:8010 pnpm exec playwright test e2e/live.spec.ts
cd apps/web && pnpm lint && pnpm build
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
| | `WEB_ORIGIN` | The only origin CORS allows |
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
| | `LLM_PROVIDER` | `none` (default: no LLM calls, every step uses its fallback), `anthropic` (live LLM layer, only with `ANTHROPIC_API_KEY`) or `openai` (offline question drafting only). See [LLM layer](#llm-layer-off-by-default) |
| | `ANTHROPIC_API_KEY` | Claude API key: empty in `.env.example`; set it only to switch the LLM layer on |
| | `LLM_EXTRACTION_MODEL`, `LLM_PHRASING_MODEL`, `LLM_EXPLANATION_MODEL`, `LLM_EFFORT` | Live LLM models (`claude-haiku-5-5`) and effort (`low`) |
| | `LLM_TIMEOUT_SECONDS`, `LLM_DAILY_SPEND_CAP_USD` | Per-call wall-clock timeout (4 s) and daily estimated spend cap (USD, India-time day); past either, the fallback is used |
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
