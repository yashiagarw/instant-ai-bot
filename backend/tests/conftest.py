"""Shared fixtures. Tests run against TEST_DATABASE_URL (a separate *_test database),
migrated to head with Alembic at the start of the session."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import database_is_up, get_session, make_engine
from app.main import create_app

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    base = get_settings()
    # Keyword matching by default: API tests never load the embedding model (hybrid search has its own tests).
    return base.model_copy(
        update={
            "database_url": base.test_database_url,
            "environment": "test",
            "diagnosis_search": "keyword",
            "llm_provider": "none",
            # Limits counted per test app, not in the developer's Redis (tests/test_hardening.py tests the Redis one).
            "rate_limit_backend": "memory",
            "turnstile_secret_key": "",
            "sentry_dsn": "",
            "log_format": "console",
        }
    )


@pytest.fixture(autouse=True)
def notify_queue(test_settings):
    """Every test: notifications are recorded on an in-memory queue (never the developer's Redis / worker), with the
    test settings. Tests that send them use tests.notify_helpers.drain()."""
    from app.notify import queue as nq
    from app.notify import service as notify

    q = nq.RecordingQueue()
    nq.set_queue(q)
    notify.use_settings(test_settings)
    yield q
    nq.set_queue(None)
    notify.use_settings(None)


@pytest.fixture(scope="session")
def test_engine(test_settings):
    url = make_url(test_settings.database_url)
    # Guard: never run destructive test setup against a non-test database.
    if not (url.database or "").endswith("_test"):
        pytest.fail(f"TEST_DATABASE_URL must point at a database ending in '_test', got '{url.database}'")
    engine = make_engine(test_settings.database_url, connect_timeout=3)
    if not database_is_up(engine):
        pytest.fail(
            f"Test database not reachable at {url.render_as_string(hide_password=True)}. "
            "Start it with: docker compose up -d db"
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def alembic_config(test_settings) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", test_settings.database_url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def migrated_db(test_engine, alembic_config):
    """Test database reset to an empty schema and migrated to head."""
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    return test_engine


@pytest.fixture
def db_connection(migrated_db):
    """A connection inside a transaction that is rolled back after the test.
    Test modules can override this fixture (e.g. to start from seeded data)."""
    with migrated_db.connect() as conn:
        trans = conn.begin()
        yield conn
        trans.rollback()


@pytest.fixture
def db_session(db_connection):
    """ORM session on the test connection. commit() only releases a savepoint, so nothing
    a test writes survives the test."""
    with Session(bind=db_connection, join_transaction_mode="create_savepoint") as session:
        yield session


@pytest.fixture
def client(test_settings, db_session):
    """API client whose requests use the test's db_session."""
    app = create_app(test_settings)
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.state.engine.dispose()
