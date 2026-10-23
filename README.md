# Instant Mechanic: AI car diagnosis

AI car diagnosis chatbot and mechanic assistance platform for [Instant Mechanic](https://instantmechanic.online), Delhi NCR. Project rules are in [CLAUDE.md](CLAUDE.md).

## Layout

| Path | What |
|---|---|
| `apps/web` | Customer site: Next.js (App Router), TypeScript, Tailwind CSS v4, shadcn/ui |
| `backend/app` | FastAPI app. Modules: `vehicles`, `knowledge`, `diagnosis`, `requests` |
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

## First-time setup

```bash
# 1. Env files (defaults work for local development)
cp .env.example .env
cp backend/.env.example backend/.env
cp apps/web/.env.example apps/web/.env.local

# 2. Database: PostgreSQL 16 + pgvector, plus an autocare_test database for pytest
docker compose up -d db

# 3. Backend
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.vehicles.seed      # vehicle catalogue from data/catalogue/vehicles.yaml
uv run python -m app.knowledge.importer --all   # the 18 datasets (first run downloads a ~470 MB embedding model)
cd ..

# 4. Web
cd apps/web
pnpm install
cd ../..
```

## Run

Two terminals:

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
# http://localhost:8000/api/health  ->  {"status":"ok","database":"ok"}
# http://localhost:8000/docs        ->  API docs
# http://localhost:8000/api/vehicles/search?q=swift%202019%20petrol
```

```bash
cd apps/web && pnpm dev
# http://localhost:3000
```

## Test

```bash
docker compose up -d db                      # backend tests need the database
cd backend && uv run pytest                  # API, settings, migrations, engine rules
cd backend && uv run ruff check . && uv run ruff format --check .
cd apps/web && pnpm test                     # Vitest
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
| `apps/web/.env.local` | `NEXT_PUBLIC_API_URL` | Backend base URL for the browser |
