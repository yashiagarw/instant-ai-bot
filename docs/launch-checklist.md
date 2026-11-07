# Launch checklist

Phase 5.6. Every line needs a name and a date before the public launch. **Blocking** lines stop the launch; the
others can follow in the first weeks if the owner agrees. Keep this file updated in git (it is the record).

## 1. Domains, DNS, HTTPS
| | Item | How to check | Who / date |
|---|---|---|---|
| Blocking | A records for diagnose., admin., api., files.instantmechanic.online (and the .staging ones) point at the servers; @ and www unchanged (the existing site) | `dig +short diagnose.instantmechanic.online` | |
| Blocking | HTTPS on all four hosts with valid certificates (Caddy, Let's Encrypt) | `sh scripts/deploy/smoke.sh ...` passes; SSL Labs grade A for api. and diagnose. | |
| Blocking | HTTP redirects to HTTPS; HSTS sent (`HSTS_MAX_AGE=31536000`) | smoke test | |
| | CAA record allows letsencrypt.org (and zerossl.com) | `dig CAA instantmechanic.online` | |
| | Link from instantmechanic.online to diagnose.instantmechanic.online on the existing site | open the site | |
| | Email DNS (SPF, DKIM, DMARC) for the alert sender | provider dashboard says verified (docs/notifications-setup.md) | |

## 2. Servers and secrets
| | Item | How to check | Who / date |
|---|---|---|---|
| Blocking | Production and staging set up as in [server-setup.md](server-setup.md): deploy user, SSH key only, firewall 22/80/443, swap, automatic security updates, Docker | `sudo ufw status`; `ssh root@<ip>` refused | |
| Blocking | Every production secret is **new** (not from a laptop or staging): AUTH_SECRET, STAFF_TOTP_KEY, MECHANIC_DOCS_KEY, POSTGRES_PASSWORD, S3 keys, WHATSAPP_VERIFY_TOKEN, VAPID keys, TURNSTILE keys | compare with staging: no value is the same | |
| Blocking | GitHub environments: `staging` and `production`, production with required reviewer (you) and only `main` allowed | Settings > Environments | |
| Blocking | GitHub secrets and variables per environment (README "Phase 5.6") | a push to main deploys staging; production waits for approval | |
| | The servers pull with a classic token that has only `read:packages`, one per server, expiry in the calendar | `docker login` works; token list on GitHub | |
| | [runbooks/secret-rotation.md](runbooks/secret-rotation.md) reviewed; password manager has every secret and the backup key | | |

## 3. Backups, monitoring, rollback
| | Item | How to check | Who / date |
|---|---|---|---|
| Blocking | Backups verified on production: a nightly backup exists off-site, and the restore test passed on it | [runbooks/restore.md](runbooks/restore.md) table has a production row | |
| Blocking | The age private key for backups is in the password manager and on an offline copy, reachable by two people | | |
| Blocking | Monitoring alerts tested: uptime checks on the four URLs ([runbooks/uptime.md](runbooks/uptime.md)) alert by SMS/WhatsApp **and** email; stop the API on staging and see the alert arrive | | |
| Blocking | Sentry set up (DSNs for API, web, admin; `SENTRY_ENVIRONMENT=production`), a test error seen, alert rule to email | | |
| Blocking | **Rollback rehearsed on staging**: deploy a commit, then Actions > "Deploy (manual)" > rollback; also once with a release that added a migration (readiness then shows `"migrations":"ahead"`) | the staging smoke test passes after the rollback | |
| | A production deploy observed end to end (approval, smoke test), with the deploy runbook | [runbooks/deploy.md](runbooks/deploy.md) | |
| | Load test passed on staging: `STAGING_SSH=deploy@<staging> sh scripts/loadtest.sh staging` (200 sessions, every step p95 < 800 ms) | loadtest/results/ | |

## 4. Messaging and calls (India)
| | Item | How to check | Who / date |
|---|---|---|---|
| Blocking | **MSG91 for customer login** (OTP): account, DLT entity and sender id, the OTP template approved on DLT and added in MSG91; `SMS_PROVIDER=msg91`, `MSG91_AUTH_KEY`, `MSG91_TEMPLATE_ID`, `MSG91_SENDER_ID` | log in on production with a real phone | |
| Blocking | **SMS DLT templates approved** for the notifications (job offer, assigned, en route, arrived, completed; English and Hindi): `MSG91_TPL_*` set | Admin > a test request: the SMS arrives | |
| Blocking | **WhatsApp templates approved** (Meta Business: the five templates, both languages), number verified, webhook set to `https://api.instantmechanic.online/api/webhooks/whatsapp` | docs/notifications-setup.md; a test message arrives | |
| Blocking | **Masked calling number live** (Exotel): KYC done, the virtual number (`EXOTEL_CALLER_ID`) and keys set; a mechanic calls a customer through it | the call connects, the customer sees the virtual number | |
| Blocking | **Real `HELPLINE_NUMBER`** (still the placeholder `+91-00000-00000`): a staffed number, shown on every safety screen and the request form | GET `/api/service-requests/config` | |
| | Web push keys (VAPID) generated for production | "Turn on alerts" works on a phone | |

## 5. Legal and content
| | Item | How to check | Who / date |
|---|---|---|---|
| Blocking | **Legal pages live without placeholders**: company name, address, grievance officer name/email/phone (`apps/web/src/components/legal/legal.tsx`, `PLACEHOLDER`), reviewed by a lawyer | /privacy, /terms, /disclaimer show no [BRACKETS] | |
| Blocking | **Mechanic sign-off of the safety rules** listed in `REVIEW_NOTES.md` (a qualified mechanic reads and signs each one) | REVIEW_NOTES.md has the name and date | |
| Blocking | **About 20 real mechanic test cases per Phase 1 category** written by mechanics, saved as real cases (Admin > Quality) and passing the eval | Quality page; `python -m app.datasets.ci_eval run --scope full` | |
| | **Hindi review**: every text in [hindi-review.md](hindi-review.md) checked by a native speaker; Hindi tiles marked reviewed | the "Checked" column is filled | |
| | **84 rough pincode centres** (`data/schema/pincode_centres.yaml`, accuracy 1, `reviewed: false`): check them (or accept, for distances only) | file says `reviewed: true` | |
| | **3,127 prices without a source or a check date**: add sources and dates (Admin > Parts & prices) or keep them labelled as estimates | Admin > Parts & prices filter "no source" | |
| | Customer support team trained: the admin app (queue, request, dispatch, refunds of time), the safety escalation path, the helpline script, the rollback contact | a dry run with a test request | |

## 6. Services and keys
| | Item | How to check | Who / date |
|---|---|---|---|
| Blocking | **Turnstile** (Cloudflare): site key (GitHub variable `NEXT_PUBLIC_TURNSTILE_SITE_KEY`) and secret (`TURNSTILE_SECRET_KEY`) for production's domains | the request form shows the check | |
| | **Stadia Maps** key for the admin map (`NEXT_PUBLIC_MAP_KEY`, domain-restricted to admin.instantmechanic.online) | the dispatch map shows tiles | |
| | **Sentry** (see section 3) | | |
| | **Decision: turn on the AI answers?** (`LLM_PROVIDER=anthropic` and an API key). Off by default: the app works without them. If yes: a budget limit at the provider, `RETENTION_LLM_DAYS`, and the eval with `--extraction llm` passes | written decision with a date | |

## 7. Launch day
- [ ] Deploy outside 18:00-22:00 India time; the last staging deploy of the same commit passed its smoke test.
- [ ] Approve production; the pipeline's smoke test passes (it rolls back by itself if not).
- [ ] Do one real diagnosis on a phone, one request, one mechanic acceptance; check the alert email and SMS.
- [ ] Watch Sentry and the uptime monitor for the first two hours. Rollback: [runbooks/rollback.md](runbooks/rollback.md).
