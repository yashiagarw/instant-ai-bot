# Secret rotation

Rotate a secret when it may have leaked, when someone who knew it leaves, and yearly. Secrets live only in
`.env.prod` and `backend/.env.prod` on the server (and the password manager); never in git.

After changing `backend/.env.prod`: `dcp up -d api worker` (recreates them with the new values).
After changing build-time `NEXT_PUBLIC_*` values: rebuild web / admin ([deploy.md](deploy.md)).

| Secret | How to rotate | Effect on users |
|---|---|---|
| `POSTGRES_PASSWORD` | `dcp exec db psql -U autocare -c "ALTER USER autocare PASSWORD '<new>'"`, then set it in `.env.prod`, `dcp up -d` | none |
| `AUTH_SECRET` | new value (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`) | login codes in flight stop working; WhatsApp opt-in phone hashes stop matching (customers opt in again) |
| `STAFF_TOTP_KEY` | new Fernet key | **every staff member sets up two-factor again**: announce it first |
| `MECHANIC_DOCS_KEY` | decrypt and re-encrypt documents with a script first; never just replace it | documents become unreadable if replaced |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | SeaweedFS: change both in `backend/.env.prod`, `dcp up -d storage api worker`; cloud: create the new key, deploy, delete the old one | none |
| `WHATSAPP_TOKEN` | Meta Business settings > System users > new token, deploy, revoke the old | none |
| `WHATSAPP_APP_SECRET` | App settings > Basic > Reset; deploy at once (webhooks fail in between) | presses in that minute are retried by Meta |
| `MSG91_AUTH_KEY`, `RESEND_API_KEY` / `SMTP_PASSWORD`, `EXOTEL_API_TOKEN` | new key in the provider's dashboard, deploy, delete the old | none |
| `VAPID_PRIVATE_KEY` | avoid: browsers must turn alerts on again | alerts stop until re-enabled |
| `TURNSTILE_SECRET_KEY` | Cloudflare dashboard > Turnstile > rotate secret, deploy | none |
| `SENTRY_DSN` | Sentry > Client keys > new key, deploy (web/admin: rebuild for `NEXT_PUBLIC_SENTRY_DSN`), disable the old | none |
| Backup key (`BACKUP_AGE_RECIPIENT`) | new key pair ([restore.md](restore.md)), new public key in `.env.prod`; **keep the old private key 30 days** (older backups need it) | none |
| `BACKUP_S3_*` | new bucket key, deploy, delete the old | none |
| Staff passwords | each person changes theirs; a super admin can force it (Users page) | |

After any rotation: check [deploy.md](deploy.md) "Check", and look for errors mentioning the provider in the logs.
