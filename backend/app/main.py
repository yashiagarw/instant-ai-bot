"""FastAPI entry point: uv run uvicorn app.main:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.vehicles import api as vehicles_api


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Instant Mechanic API", version="0.1.0")

    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url, settings.db_connect_timeout)
    app.state.session_factory = make_session_factory(app.state.engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        allow_credentials=False,
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(vehicles_api.router, prefix="/api")
    return app


app = create_app()
