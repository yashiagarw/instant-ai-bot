# Uptime monitoring

## Health endpoints
| URL | Healthy | Meaning |
|---|---|---|
| `https://api.instantmechanic.online/api/health/live` | 200 | the API process answers (no dependencies) |
| `https://api.instantmechanic.online/api/health/ready` | 200, `"status":"ok"` | database answers and migrations are at head; `"degraded"` = Redis down (jobs wait) |
| `https://instantmechanic.online/healthz` | 200 | the website's server answers |
| `https://admin.instantmechanic.online/healthz` | 200 | the admin app's server answers |
| `https://files.instantmechanic.online/healthz` | 200 | photo storage (SeaweedFS profile only) |

Health checks are exempt from the rate limits. The worker has no URL: `dcp ps worker` shows its Docker health
(`arq --check`), and the readiness check reports Redis.

## Set up (free tier is enough)
Use an external monitor such as **Better Stack** or **UptimeRobot** (both have free plans with 1-3 minute checks):
1. HTTP monitor on `/api/health/ready`, every 1 minute, expect status 200 **and** the keyword `"status":"ok"`; alert
   after 2 failures. A second monitor on `/healthz` of the website.
2. Alerts to the on-call phone (SMS / app push) and the team email. Add a second person.
3. A status page is optional.
4. TLS expiry: most monitors warn 14 days before; Caddy renews at 30 days, so a warning means renewal failed.

Sentry: alert rule "a new issue is created" and "more than 20 events in 5 minutes" to the same people.

## When it alerts
1. `dcp ps`: which service is not healthy?
2. `dcp logs --since 15m <service>`: the last errors (JSON; `grep '"level": "ERROR"'`).
3. Common causes: disk full (`df -h`; old images: `docker image prune`), database down (`dcp restart db`, then
   check `dcp logs db`), a bad deploy ([rollback.md](rollback.md)), certificate renewal (Caddy logs; DNS still
   pointing here?).
4. Readiness says `"migrations":"behind"`: a migration did not run: `dcp logs migrate`, fix, `dcp up -d`.
