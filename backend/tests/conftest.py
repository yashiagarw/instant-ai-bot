"""Shared fixtures. Tests run against TEST_DATABASE_URL (a separate *_test database),
migrated to head with Alembic at the start of the session."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.db import database_is_up, make_engine
from app.main import create_app

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    base = get_settings()
    return base.model_copy(update={"database_url": base.test_database_url, "environment": "test"})


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
def client(test_settings, migrated_db):
    app = create_app(test_settings)
    with TestClient(app) as c:
        yield c
    app.state.engine.dispose()
