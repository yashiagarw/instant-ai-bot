from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text


def test_single_head_is_the_initial_migration(alembic_config):
    heads = ScriptDirectory.from_config(alembic_config).get_heads()
    assert heads == ["0001"]


def test_database_is_at_head(migrated_db):
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001"


def test_downgrade_and_upgrade_round_trip(migrated_db, alembic_config):
    command.downgrade(alembic_config, "base")
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM alembic_version")).scalar_one() == 0
    command.upgrade(alembic_config, "head")
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001"
