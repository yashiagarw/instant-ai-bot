"""FastAPI entry point: uv run uvicorn app.main:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.accounts import api as accounts_api
from app.admin import api as admin_api
from app.admin.deps import check_admin_routes
from app.admin.security import fernet
from app.api import health
from app.config import Settings, get_settings
from app.datasets import api as datasets_api
from app.db import make_engine, make_session_factory
from app.diagnosis import api as diagnosis_api
from app.estimates import api as estimates_api
from app.knowledge.edits import api as knowledge_admin_api
from app.mechanics import admin_api as mechanics_admin_api
from app.notify import api as notify_api
from app.notify import service as notify
from app.parts import admin_api as parts_admin_api
from app.parts import api as parts_api
from app.quality import api as quality_api
from app.requests import admin_api as requests_admin_api
from app.requests import api as requests_api
from app.uploads import admin_api as media_admin_api
from app.uploads import api as uploads_api
from app.vehicles import admin_api as vehicles_admin_api
from app.vehicles import api as vehicles_api


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.environment == "production" and settings.auth_secret.startswith("dev-only"):
        raise RuntimeError("Set AUTH_SECRET to a long random value in production")
    fernet(settings)  # STAFF_TOTP_KEY must be valid (and set, in production) before staff can sign in
    app = FastAPI(title="Instant Mechanic API", version="0.1.0")

    app.state.settings = settings
    notify.use_settings(settings)  # request events queue notifications with these settings
    app.state.engine = make_engine(settings.database_url, settings.db_connect_timeout)
    app.state.session_factory = make_session_factory(app.state.engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o for o in (settings.web_origin, settings.admin_origin) if o],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        allow_credentials=True,  # login cookies; only WEB_ORIGIN and ADMIN_ORIGIN may send them
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
    app.include_router(admin_api.router, prefix="/api")
    app.include_router(datasets_api.router, prefix="/api")
    app.include_router(knowledge_admin_api.router, prefix="/api")
    app.include_router(vehicles_admin_api.router, prefix="/api")
    app.include_router(parts_admin_api.router, prefix="/api")
    app.include_router(media_admin_api.router, prefix="/api")
    app.include_router(mechanics_admin_api.router, prefix="/api")
    app.include_router(requests_admin_api.router, prefix="/api")
    app.include_router(quality_api.router, prefix="/api")
    app.include_router(notify_api.router, prefix="/api")
    app.include_router(notify_api.me_router, prefix="/api")
    app.include_router(notify_api.webhook_router, prefix="/api")
    app.include_router(notify_api.admin_router, prefix="/api")
    app.include_router(media_admin_api.public_router)  # /media/uploaded/<sha1>.jpg (before the /media files below)
    # every /api/admin route runs the access check with a permission
    check_admin_routes(
        app,
        admin_api.router,
        datasets_api.router,
        knowledge_admin_api.router,
        vehicles_admin_api.router,
        parts_admin_api.router,
        media_admin_api.router,
        mechanics_admin_api.router,
        requests_admin_api.router,
        quality_api.router,
        notify_api.admin_router,
    )
    if settings.media_dir.is_dir():
        app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
    return app


app = create_app()
