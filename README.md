# Instant Mechanic: AI car diagnosis

AI car diagnosis chatbot and mechanic assistance platform for [Instant Mechanic](https://instantmechanic.online), Delhi NCR. Project rules are in [CLAUDE.md](CLAUDE.md).

## Layout

| Path | What |
|---|---|
| `apps/web` | Customer site: Next.js (App Router), TypeScript, Tailwind CSS v4, shadcn/ui |
| `backend/app` | FastAPI app. Modules: `vehicles`, `knowledge`, `diagnosis`, `requests`, `notify` (email alerts) |
| `backend/engine` | Diagnosis engine, plain Python with no web imports |
| `backend/alembic` | Database migrations |
| `data/raw` | The 18 original Excel datasets. Never edit |
| `data/schema` | Manifest, column aliases, taxonomy, import rules |
| `data/catalogue` | Vehicle catalogue seed (editable YAML) |
| `docs` | Dataset profile, findings, data model |
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
uv run alembic upgrade head                          # all migrations (0001 … 0006)
uv run python -m app.vehicles.seed                   # vehicle catalogue from data/catalogue/vehicles.yaml
uv run python -m app.knowledge.importer --all        # the 18 datasets (first run downloads a ~470 MB model)
uv run python -m app.knowledge.questions load --all  # approved question flows + safety rules (data/review/questions)
uv run python -m app.knowledge.merges apply          # approved duplicate-fault merges (data/review/merges.yaml)
uv run python -m app.knowledge.embeddings sync       # search index: embeds only new or changed texts
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
cd apps/web && pnpm test                     # Vitest component tests
cd apps/web && pnpm test:e2e                 # Playwright, phone + desktop (builds and serves the app on :3100;
                                             # the API is mocked, no backend needed)
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
| | `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, … | Offline question drafting only; never used by the live app |
| `apps/web/.env.local` | `NEXT_PUBLIC_API_URL` | Backend base URL for the browser |

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
