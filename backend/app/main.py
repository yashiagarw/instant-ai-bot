"""FastAPI entry point: uv run uvicorn app.main:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.accounts import api as accounts_api
from app.api import health
from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.diagnosis import api as diagnosis_api
from app.estimates import api as estimates_api
from app.parts import api as parts_api
from app.requests import api as requests_api
from app.uploads import api as uploads_api
from app.vehicles import api as vehicles_api


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.environment == "production" and settings.auth_secret.startswith("dev-only"):
        raise RuntimeError("Set AUTH_SECRET to a long random value in production")
    app = FastAPI(title="Instant Mechanic API", version="0.1.0")

    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url, settings.db_connect_timeout)
    app.state.session_factory = make_session_factory(app.state.engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        allow_credentials=True,  # login cookies (HttpOnly, SameSite=Lax); only WEB_ORIGIN may send them
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(vehicles_api.router, prefix="/api")
    app.include_router(diagnosis_api.categories_router, prefix="/api")
    app.include_router(diagnosis_api.router, prefix="/api")
    app.include_router(requests_api.router, prefix="/api")
    app.include_router(parts_api.router, prefix="/api")
    app.include_router(estimates_api.router, prefix="/api")
    app.include_router(accounts_api.auth_router, prefix="/api")
    app.include_router(accounts_api.me_router, prefix="/api")
    app.include_router(accounts_api.requests_router, prefix="/api")
    app.include_router(uploads_api.router, prefix="/api")
    if settings.media_dir.is_dir():
        app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
    return app


app = create_app()
