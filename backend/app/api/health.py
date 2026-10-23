from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db import database_is_up

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> JSONResponse:
    """Liveness plus a database check. 200 when Postgres answers, 503 otherwise."""
    if database_is_up(request.app.state.engine):
        return JSONResponse({"status": "ok", "database": "ok"})
    # No error details in the response: they can leak connection info.
    return JSONResponse({"status": "error", "database": "unavailable"}, status_code=503)
