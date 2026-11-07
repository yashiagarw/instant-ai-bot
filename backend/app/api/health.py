"""Health checks.

    GET /api/health        the database answers (Docker's health check and Phase 1 scripts; unchanged)
    GET /api/health/live   the process is up (no dependencies: restart it if this fails)
    GET /api/health/ready  ready to serve: the database answers and its migrations are at head (503 otherwise);
                           Redis is reported, but its loss only degrades (jobs wait, limits fall back to memory).
                           "migrations": "ahead" (still ready) = the database has a migration this code does not
                           know: the previous release after a rollback, which ignores the new columns and tables
                           (docs/runbooks/rollback.md). The database is never downgraded automatically.

No error details in the answers: they can leak connection info. docs/runbooks/uptime.md says what to watch.
"""

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import database_is_up

router = APIRouter(tags=["health"])
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@lru_cache
def migration_head() -> str | None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads()
    return heads[0] if len(heads) == 1 else None


@lru_cache
def migration_revisions() -> frozenset[str]:
    """Every migration this code has."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return frozenset(s.revision for s in ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).walk_revisions())


@router.get("/health")
def health(request: Request) -> JSONResponse:
    """Liveness plus a database check. 200 when Postgres answers, 503 otherwise."""
    if database_is_up(request.app.state.engine):
        return JSONResponse({"status": "ok", "database": "ok"})
    return JSONResponse({"status": "error", "database": "unavailable"}, status_code=503)


@router.get("/health/live")
def live() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _schema(engine) -> str:
    try:
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        return "unavailable"
    if current == migration_head():
        return "ok"
    # A revision this code does not have: a newer release migrated, then was rolled back (Phase 5.6).
    return "behind" if current in migration_revisions() or current is None else "ahead"


def _redis(url: str) -> str:
    try:
        from app.ratelimit import _redis as client

        return "ok" if client(url).ping() else "unavailable"
    except Exception:
        return "unavailable"


@router.get("/health/ready")
def ready(request: Request) -> JSONResponse:
    state = request.app.state
    database = "ok" if database_is_up(state.engine) else "unavailable"
    schema = _schema(state.engine) if database == "ok" else "unknown"
    redis = _redis(state.settings.redis_url) if state.settings.redis_url else "not configured"
    ok = database == "ok" and schema in ("ok", "ahead")
    body = {
        "status": ("ok" if redis == "ok" else "degraded") if ok else "error",
        "database": database,
        "migrations": schema,
        "redis": redis,
    }
    return JSONResponse(body, status_code=200 if ok else 503)
