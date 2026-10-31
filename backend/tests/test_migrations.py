from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

import app.models  # noqa: F401
from app.db import Base

HEAD = "0013"


def test_single_head(alembic_config):
    heads = ScriptDirectory.from_config(alembic_config).get_heads()
    assert heads == [HEAD]


def test_database_is_at_head(migrated_db):
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD


def test_downgrade_and_upgrade_round_trip(migrated_db, alembic_config):
    command.downgrade(alembic_config, "base")
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM alembic_version")).scalar_one() == 0
    command.upgrade(alembic_config, "head")
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD


def test_models_match_the_migrations(migrated_db):
    """Autogenerate finds nothing to do: the SQLAlchemy models and the migrations agree."""
    with migrated_db.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_extensions_enabled(migrated_db):
    with migrated_db.connect() as conn:
        names = set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert {"vector", "pg_trgm"} <= names
