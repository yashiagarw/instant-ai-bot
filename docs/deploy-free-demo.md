# Free demo deployment (Vercel + Render + Neon + Upstash)

An extra, zero-cost way to show the app to testers. It is **not** production: the docker-compose + SSH path
([server-setup.md](server-setup.md), README "Phase 5.6") stays the real deployment and is unchanged.

| Piece | Service (free plan) | What runs there |
|---|---|---|
| Customer website (`apps/web`) | Vercel Hobby | Next.js; `/api/*` and `/media/*` are rewritten to Render |
| Admin app (`apps/admin`) | Vercel Hobby (a second project) | Next.js; same rewrites |
| API | Render free web service, 512 MB | `backend/Dockerfile.lite`: LITE mode, background jobs in-process |
| Database | Neon free Postgres (pgvector) | the published dataset version + catalogues only |
| Redis | Upstash free | rate-limit counters |

## What is different from the full deployment

| Switch (API) | Demo | Why |
|---|---|---|
| `EMBEDDING_MODEL=none` (LITE) | torch and the model are never installed or loaded | 512 MB RAM. Search = full text + spelling correction + Hinglish forms of Hindi text. Measured: same safety recall, top-3 within 0.1 point (README "Free demo") |
| `BACKGROUND_JOBS=api` | notification sweep, offer expiry / auto-offer / escalation and retention run on a thread in the API | Render free has no background worker |
| `DATASET_JOBS_ENABLED=false` | upload, rebuild, eval, publish answer 503; the admin Datasets page says so | they need the worker and the embedding model |
| `PHOTO_UPLOADS_ENABLED=false` | the photo step is hidden | no storage bucket (no card needed) |
| `SHOW_PICTURES=false` | no fault/part pictures | the server has no `data/media` |
| `ENVIRONMENT=demo` | real secrets required (as production), but console SMS, WhatsApp, calls and email are allowed | production refuses console senders |
| `HELPLINE_NUMBER` empty | the request form shows only the **112** emergency line | no placeholder number is shown |
| Turnstile, Sentry | off (leave the keys empty) | |

Web and admin: `API_PROXY_TARGET` (the Render address) makes the browser call the API on the app's own domain, so
the login cookies are first-party on `*.vercel.app`; the CSP then allows only `'self'` for the API.
`NEXT_PUBLIC_DEMO=1` shows a **Demo** banner on every page and adds `noindex` (meta robots and `X-Robots-Tag`).

## Free-plan limits (check the providers' pricing pages; they change)
- **Render free**: the service **sleeps after 15 minutes without traffic**; the next visit waits about a minute while
  it starts (first load slow). While it sleeps no background job runs: offers expire and notifications go out when it
  wakes. 750 instance hours a month; no persistent disk (nothing is stored on it); builds can be slow.
- **Vercel Hobby**: **non-commercial, personal use only** under Vercel's terms. A demo of a company's product may
  count as commercial use: for anything beyond private testing, move to Vercel Pro (or the docker-compose servers).
  Preview deployments cannot log in (their address is not `WEB_ORIGIN` / `ADMIN_ORIGIN`): use the production URLs.
- **Neon free**: 0.5 GB of storage per project (the demo data is about 150 MB), the compute suspends when idle (the
  first query after that takes a moment), a monthly compute-hour allowance.
- **Upstash free**: a daily/monthly command allowance and 256 MB. Only rate limits use it; if Redis is unreachable the
  API counts in memory instead.

## 0. Before you start
- A GitHub account with access to this repository, and accounts on Render, Vercel, Neon and Upstash (sign in with
  GitHub; none needs a card for these plans).
- On your Mac: the repo, `uv`, Docker running with your local database (`docker compose up -d db`) holding the
  published dataset (v38).
- A password manager entry "IM free demo" for every value below. **Fresh secrets only**: never copy anything from
  `backend/.env`, `.env.prod` or `backend/.env.prod`.

Generate the three secrets on your Mac (each prints one value; paste each into the password manager):
```bash
cd backend
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"                              # AUTH_SECRET
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # STAFF_TOTP_KEY
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # MECHANIC_DOCS_KEY
```
Keep `STAFF_TOTP_KEY`: changing it later means setting up two-factor again for every staff account.

## 1. Neon (database)
1. neon.tech > **New project**: name `im-demo`, Postgres **16**, region **AWS Asia Pacific (Singapore)** (closest
   to Delhi and to Render's Singapore region).
2. Project dashboard > **Connect**: database `neondb`, role `neondb_owner`, **turn "Connection pooling" off** (the
   direct address; the app keeps its own small pool and takes advisory locks). Copy the connection string.
3. Turn it into the form the app uses: replace `postgresql://` with `postgresql+psycopg://` and keep
   `?sslmode=require` (and `&channel_binding=require` if present). This is **DATABASE_URL** (password manager).

## 2. Upstash (Redis)
1. console.upstash.com > Redis > **Create database**: name `im-demo`, type Regional, region **ap-south-1 (Mumbai)**
   or Singapore, TLS on, eviction off.
2. On the database page, copy the **`rediss://` URL** (Connect > "Redis URL", it contains the password). This is
   **REDIS_URL**.

## 3. Load the data into Neon (from your Mac)
Only the published dataset version (v38) and the vehicle and parts catalogues are copied, by an explicit allowlist
(`backend/app/demo_export.py`). **Never copied**: customers, test requests, diagnosis sessions, mechanics, staff
users, notifications, uploads, the audit log, LLM calls, other dataset versions or drafts. Search rows are copied
only for the model v38 is served with.

Put the Neon address in a shell variable without it landing in your shell history:
```bash
cd backend
read -rs NEON_URL && export NEON_URL        # paste DATABASE_URL from step 1, press Enter (nothing is shown)
```
Then:
```bash
DATABASE_URL="$NEON_URL" uv run alembic upgrade head          # the schema (and pgvector, and the staff roles)
uv run python -m app.demo_export --target "$NEON_URL"         # dry run: rows per table, nothing written
uv run python -m app.demo_export --target "$NEON_URL" --copy  # copy, check every count, print the database size
```
The source is your local database (`DATABASE_URL` from `backend/.env`; read only). The copy runs in one transaction,
checks every table's count against the source, checks that no people/activity table has rows, and prints the size
(about 150 MB). It refuses a target that already has data: to start again, delete the Neon branch's database
(Neon > Branches > reset or create a new branch) and repeat this step.

Pictures (`data/media`) are **not** needed: the demo runs with `SHOW_PICTURES=false` (see "Later" for adding them).

## 4. Render (API)
1. dashboard.render.com > **New > Web Service** > connect GitHub > choose this repository.
2. Settings:
   - Name `im-api` (the address becomes `https://im-api.onrender.com`; Render may add a suffix: use what it shows).
   - Region **Singapore**. Branch `main` (or the branch you want to show).
   - Language **Docker**. **Dockerfile Path** `backend/Dockerfile.lite`, **Docker Build Context Directory** `.`
     (the repository root; Advanced section).
   - Instance type **Free**.
   - Health Check Path `/api/health/live` (Advanced).
3. Environment variables (Advanced > Add environment variable). The image already sets the demo switches
   (`EMBEDDING_MODEL=none`, `BACKGROUND_JOBS=api`, `DATASET_JOBS_ENABLED=false`, `PHOTO_UPLOADS_ENABLED=false`,
   `SHOW_PICTURES=false`, `ENVIRONMENT=demo`, `TRUST_FORWARDED_FOR=true`, `MIGRATE_ON_START=true`,
   `LLM_PROVIDER=none`); add:

   | Variable | Value | Where it comes from |
   |---|---|---|
   | `DATABASE_URL` | `postgresql+psycopg://...neon.tech/neondb?sslmode=require` | step 1 |
   | `REDIS_URL` | `rediss://default:...@....upstash.io:6379` | step 2 |
   | `AUTH_SECRET` | 64 random characters | step 0 (fresh) |
   | `STAFF_TOTP_KEY` | a Fernet key | step 0 (fresh) |
   | `MECHANIC_DOCS_KEY` | a Fernet key | step 0 (fresh) |
   | `WEB_ORIGIN` | `https://<web project>.vercel.app` | step 5 (set a placeholder now, fix after step 5) |
   | `ADMIN_ORIGIN` | `https://<admin project>.vercel.app` | step 5 (same) |
   | `COOKIE_SECURE` | `true` | |
   | `HELPLINE_NUMBER` | *(empty)* | shows only 112 |
   | `SMS_PROVIDER`, `WHATSAPP_PROVIDER`, `CALL_PROVIDER`, `PUSH_PROVIDER`, `EMAIL_PROVIDER` | `console` (the defaults; no need to add) | login codes and messages are printed in Render's **Logs** |
   | `TURNSTILE_SECRET_KEY`, `SENTRY_DSN` | leave unset | off |

4. **Create Web Service**. The first build takes several minutes. When it is live, open
   `https://<render address>/api/health/ready`: `{"status":"ok","database":"ok","migrations":"ok","redis":"ok"}`.

A customer logging in with a phone number gets no SMS: the code appears in Render > Logs (search for `[console SMS]`
and the phone number). Tell testers to ask you for it, or use the admin app, which needs no SMS.

## 5. Vercel (website and admin)
Two projects from the same repository.

**Website**: vercel.com > **Add New > Project** > import the repository.
- Project name e.g. `im-demo-web`. Framework preset **Next.js**. **Root Directory** `apps/web` ("Include files
  outside the root directory" stays on: the shared `packages/ui` is needed). Build and install commands: the
  defaults (Vercel detects pnpm from the lockfile).
- Environment variables (Production):

  | Variable | Value |
  |---|---|
  | `API_PROXY_TARGET` | the Render address, e.g. `https://im-api.onrender.com` (no path, no trailing slash) |
  | `NEXT_PUBLIC_DEMO` | `1` |
  | `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, `NEXT_PUBLIC_SENTRY_DSN` | leave unset |

  `NEXT_PUBLIC_API_URL` is not needed (ignored when `API_PROXY_TARGET` is set). These are read at **build** time:
  after changing one, redeploy.
- **Deploy**. Note the production address (Settings > Domains, e.g. `im-demo-web.vercel.app`).

**Admin**: the same again with Root Directory `apps/admin`, project name e.g. `im-demo-admin`, the same two
variables (`NEXT_PUBLIC_MAP_PROVIDER` can stay unset: Stadia's free tiles; on a non-localhost domain Stadia may ask
you to register the domain in a free Stadia account).

**Then back on Render**: set `WEB_ORIGIN` and `ADMIN_ORIGIN` to the two exact production addresses
(`https://...vercel.app`, no trailing slash) and save (Render redeploys). Both are used for the CSRF origin check.

## 6. Create your super admin (from your Mac, against Neon)
Same as README "Create your super admin", with the demo's database and **the same `STAFF_TOTP_KEY` as on Render**
(it encrypts the two-factor secret):
```bash
cd backend
read -rs NEON_URL && export NEON_URL          # DATABASE_URL from step 1
read -rs DEMO_TOTP && export DEMO_TOTP        # STAFF_TOTP_KEY from step 0
DATABASE_URL="$NEON_URL" STAFF_TOTP_KEY="$DEMO_TOTP" \
  uv run python -m app.admin.cli create-super-admin --email you@example.com --name "Your Name"
unset NEON_URL DEMO_TOTP
```
Type a new password twice and scan the QR code with your authenticator app (use a new entry, "IM demo").
Then sign in at `https://<admin project>.vercel.app`. Invite other staff from the admin app.

## 7. Check
- Website: the black **Demo** bar at the top; pick a car, describe a problem, answer, get a result (the first visit
  after a quiet period waits for Render to wake up).
- View the page source: `<meta name="robots" content="noindex, nofollow">`;
  `curl -sI https://<web>.vercel.app | grep -i x-robots` shows `noindex, nofollow`.
- Request a mechanic: the form shows "In an emergency, call 112", no helpline number.
- Admin: sign in, Requests, Datasets ("Dataset changes are switched off on this server").
- `sh scripts/deploy/smoke.sh <web>.vercel.app <render address without https://> <admin>.vercel.app` (optional).

## Security notes for the demo
- Cookies are first-party on the Vercel domains (host-only, `Secure`; staff `SameSite=Strict`).
- The rate limits use the first `X-Forwarded-For` address (Vercel's view of the client). Someone calling the Render
  address directly could fake that header and get a fresh rate-limit bucket: acceptable for a demo; the real
  deployment has only Caddy in front.
- Do not put real customers' data into the demo: it has no backups and console SMS prints phone numbers and login
  codes into Render's logs (only people with access to the Render service can read them).

## Later (optional)
- **Custom subdomains** (e.g. `demo.instantmechanic.online`): Vercel > project > Settings > Domains > add, then the
  CNAME it shows at the DNS provider; update `WEB_ORIGIN` / `ADMIN_ORIGIN` on Render to the new addresses.
- **Customer photo upload on Cloudflare R2** (free 10 GB, no egress fees; needs a Cloudflare account, which asks for
  a card only for paid plans):
  1. Cloudflare > R2 > Create bucket `im-demo-photos` (location hint Asia Pacific). R2 > Manage API tokens > Create:
     **Object Read & Write**, only that bucket. Note the Access Key ID, Secret and the S3 endpoint
     `https://<account id>.r2.cloudflarestorage.com`.
  2. Bucket > Settings > CORS: allow origin `https://<web>.vercel.app`, methods GET, PUT, POST, header `*`.
  3. **Code change needed first**: the app's browser upload is an S3 *presigned POST* form
     (`backend/app/uploads/storage.py`), which R2 does not support. A follow-up must switch R2 to a presigned
     **PUT** (the API already checks the size after the upload).
  4. Then on Render: `PHOTO_UPLOADS_ENABLED=true`, `S3_ENDPOINT_URL` and `S3_PUBLIC_ENDPOINT_URL` = the endpoint,
     `S3_REGION=auto`, `S3_BUCKET=im-demo-photos`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`; on Vercel (web):
     `NEXT_PUBLIC_FILES_URL` = the endpoint (the CSP allows it), redeploy.
- **Pictures**: `data/media` (about 26 MB, not in git) would have to be served from storage (R2 public bucket) and
  the picture links pointed there: a follow-up; until then keep `SHOW_PICTURES=false`.
- **Dataset changes**: make them on the full deployment or locally, then repeat step 3 into a fresh Neon branch.

## Removing the demo
Render > service > Settings > Delete; Vercel > each project > Settings > Delete; Neon > project > Delete; Upstash >
database > Delete. Remove the "IM free demo" secrets from the password manager.
