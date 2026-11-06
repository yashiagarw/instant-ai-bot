# Runbooks

Step-by-step for the production server (docker-compose.prod.yml). Each assumes this helper in the repo folder:

```bash
dcp() { docker compose -f docker-compose.prod.yml --env-file .env.prod "$@"; }   # add --profile storage if SeaweedFS runs here
```

| Runbook | When |
|---|---|
| [deploy.md](deploy.md) | Shipping a new version |
| [rollback.md](rollback.md) | A deploy went wrong |
| [restore.md](restore.md) | Data lost or damaged; the monthly restore test |
| [secret-rotation.md](secret-rotation.md) | A secret leaked, a person left, or the yearly rotation |
| [uptime.md](uptime.md) | Setting up monitoring and what to do when it alerts |

Logs: `dcp logs -f --since 30m api` (JSON, one line per request or event). Find everything about one request by its id:
`dcp logs --since 2h api worker | grep <request id>` (the id is in the `X-Request-ID` response header, in Sentry's
`request_id` tag, and in every log line).
