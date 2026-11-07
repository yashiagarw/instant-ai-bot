"""The free demo's data export (app.demo_export) copies only what is on its allowlist."""

from app import demo_export
from app.db import Base, _load_all_models


def test_every_table_is_decided():
    """A new table must be put in COPY (published knowledge, catalogues) or NEVER (people, activity, drafts)."""
    _load_all_models()
    tables = set(Base.metadata.tables)
    assert not set(demo_export.COPY) & demo_export.NEVER
    assert tables - set(demo_export.COPY) - demo_export.NEVER == set()
    assert set(demo_export.COPY) | demo_export.NEVER <= tables


def test_no_personal_or_activity_table_is_copied():
    for name in ("users", "staff_users", "service_requests", "diagnosis_sessions", "mechanics", "notifications",
                 "uploads", "audit_log", "llm_calls", "otp_requests", "dataset_jobs", "knowledge_edits"):  # fmt: skip
        assert name in demo_export.NEVER and name not in demo_export.COPY


def test_version_scoped_tables_are_filtered_to_one_version():
    from sqlalchemy import Table

    for t in demo_export.tables_in_load_order():
        assert isinstance(t, Table)
        if "dataset_version_id" in t.columns or "fault_id" in t.columns:
            assert demo_export.COPY[t.name], f"{t.name} must be filtered to the exported version"
    sql = demo_export.select_sql(Base.metadata.tables["dataset_versions"])
    assert "NULL" in sql and "WHERE id =" in sql  # base / rollback ids point at versions that are not copied
