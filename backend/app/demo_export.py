"""Copy only the published dataset version and the catalogues into an empty database: the free demo on Neon
(docs/deploy-free-demo.md, "Data"). Run from your Mac:

    cd backend
    uv run python -m app.demo_export --target "postgresql://...neon.tech/neondb?sslmode=require"   # dry run: counts
    uv run python -m app.demo_export --target "postgresql://...neon..." --copy

The source is DATABASE_URL (your local database). The target must already have the schema (`alembic upgrade head`
against it, step "Data" of the guide) and no knowledge rows yet.

What is copied is an explicit allowlist (COPY): the knowledge of ONE dataset version (the published one, or
--version) and the vehicle and parts catalogues. Nothing else ever leaves your machine: no customers, requests,
diagnosis sessions, mechanics, staff, notifications, uploads, audit log, LLM calls, other dataset versions or drafts
(NEVER). tests/test_demo_export.py fails when a new table is in neither list, so it has to be decided.
"""

from __future__ import annotations

import argparse
import sys

import psycopg
from sqlalchemy import Table
from sqlalchemy.engine import make_url

from app.knowledge.importer.embed import MODEL_NAME  # no torch: the module imports it only when a model is loaded

V = "%(version)s"  # the version id, as a psycopg parameter
V_FAULTS = f"SELECT id FROM faults WHERE dataset_version_id = {V}"

# table -> SQL condition (None: every row). Order does not matter: the load follows the foreign keys.
COPY: dict[str, str | None] = {
    # catalogues (no dataset version)
    "makes": None,
    "models": None,
    "generations": None,
    "variants": None,
    "brands": None,
    "part_types": None,
    "parts": None,
    "part_images": None,
    "categories": None,
    "category_sources": None,
    "problem_groups": None,
    "problem_group_categories": None,
    "source_files": None,
    "image_labels": None,
    # the version and everything that belongs to it
    "dataset_versions": f"id = {V}",
    "faults": f"dataset_version_id = {V}",
    "fault_items": f"fault_id IN ({V_FAULTS})",
    "fault_costs": f"fault_id IN ({V_FAULTS})",
    "fault_parts": f"fault_id IN ({V_FAULTS})",
    "fault_images": f"fault_id IN ({V_FAULTS})",
    "fault_priors": f"fault_id IN ({V_FAULTS})",
    "fault_links": f"from_fault_id IN ({V_FAULTS})",
    "fault_service_charges": f"dataset_version_id = {V}",
    "customer_phrases": f"fault_id IN ({V_FAULTS})",
    "internal_notes": f"fault_id IN ({V_FAULTS})",
    "diagnosis_rules_raw": f"fault_id IN ({V_FAULTS})",
    # only the search rows of the model the version is served with (app.knowledge.embeddings.version_model)
    "embeddings": (
        f"fault_id IN ({V_FAULTS}) AND model_name = COALESCE("
        f"(SELECT embedding_model FROM dataset_versions WHERE id = {V}), '{MODEL_NAME}')"
    ),
    "safety_rules": f"dataset_version_id = {V}",
    "questions": f"dataset_version_id = {V}",
    "question_options": f"question_id IN (SELECT id FROM questions WHERE dataset_version_id = {V})",
    "option_effects": (
        "option_id IN (SELECT o.id FROM question_options o JOIN questions q ON q.id = o.question_id "
        f"WHERE q.dataset_version_id = {V})"
    ),
    "images": (
        f"id IN (SELECT image_id FROM fault_images WHERE fault_id IN ({V_FAULTS})) "
        "OR id IN (SELECT image_id FROM part_images)"
    ),
    "labour_rates": f"dataset_version_id = {V}",
    "labour_rates_research": f"dataset_version_id = {V}",
    "zone_labour_rates": f"dataset_version_id = {V}",
    "part_prices": f"dataset_version_id = {V}",
    "part_compatibility": f"dataset_version_id = {V}",
    "part_price_sources": f"dataset_version_id = {V}",
    "part_price_source_faults": (
        f"part_price_source_id IN (SELECT id FROM part_price_sources WHERE dataset_version_id = {V})"
    ),
    "price_breakdown_lines": f"dataset_version_id = {V}",
    "internal_links": f"dataset_version_id = {V}",
    "inspection_checklist_items": f"dataset_version_id = {V}",
    "towing_charge_examples": f"dataset_version_id = {V}",
}

# Never copied: people, their activity, operations, drafts, and tables the migrations fill (roles).
NEVER = {
    "users", "user_vehicles", "user_roles", "auth_sessions", "otp_requests", "account_deletions",
    "staff_users", "staff_sessions", "staff_setup_tickets", "roles",
    "diagnosis_sessions", "session_events", "session_results", "feedback", "unlisted_vehicles",
    "service_requests", "request_events", "request_notes", "request_assignments", "request_outcomes",
    "mechanics", "mechanic_availability", "mechanic_documents", "mechanic_sessions", "mechanic_skills",
    "mechanic_zones", "masked_calls", "auto_offer_settings",
    "notifications", "notification_optins", "notification_preferences", "push_subscriptions", "whatsapp_inbound",
    "uploads", "image_findings", "audit_log", "llm_calls", "golden_cases",
    "dataset_jobs", "knowledge_edits", "generated_questions",
}  # fmt: skip

# Columns written differently in the copy: the version points at nothing that is not copied.
OVERRIDES = {"dataset_versions": {"base_version_id": "NULL", "rollback_of_id": "NULL"}}


def tables_in_load_order() -> list[Table]:
    from app.db import Base, _load_all_models

    _load_all_models()
    return [t for t in Base.metadata.sorted_tables if t.name in COPY]


def libpq(url: str) -> str:
    """A SQLAlchemy URL (postgresql+psycopg://...) or a plain one, as psycopg wants it."""
    u = make_url(url)
    return u.set(drivername="postgresql").render_as_string(hide_password=False)


def published_version(src: psycopg.Connection) -> int:
    row = src.execute("SELECT id FROM dataset_versions WHERE status = 'published' ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        raise SystemExit("no published dataset version in the source database (publish one on the Datasets page)")
    return row[0]


def columns(table: Table) -> list:
    """The columns written: generated ones (e.g. embeddings.tsv, the full-text vector) are recomputed by Postgres."""
    return [c for c in table.columns if c.computed is None]


def select_sql(table: Table) -> str:
    over = OVERRIDES.get(table.name, {})
    cols = ", ".join(over.get(c.name, f'"{c.name}"') for c in columns(table))
    where = COPY[table.name]
    return f'SELECT {cols} FROM "{table.name}"' + (f" WHERE {where}" if where else "")


def run(source: str, target: str, version: int | None, copy: bool) -> int:
    with psycopg.connect(libpq(source)) as src, psycopg.connect(libpq(target)) as dst:
        v = version or published_version(src)
        status = src.execute("SELECT status FROM dataset_versions WHERE id = %s", (v,)).fetchone()
        if status is None:
            raise SystemExit(f"dataset version {v} not found in the source")
        print(f"dataset version {v} ({status[0]}) and the catalogues")
        head = (
            dst.execute("SELECT version_num FROM alembic_version").fetchone()
            if _has_table(dst, "alembic_version")
            else None
        )
        src_head = src.execute("SELECT version_num FROM alembic_version").fetchone()
        if head != src_head:
            raise SystemExit(
                f"target schema {head} differs from the source {src_head}: run alembic upgrade head on both"
            )
        busy = [n for n in ("faults", "makes") if dst.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0]]
        if busy and copy:
            raise SystemExit(f"target already has rows in {busy}: use an empty database (create a new Neon branch)")
        total = 0
        with dst.transaction():
            for table in tables_in_load_order():
                sql = select_sql(table)
                n = src.execute(f"SELECT count(*) FROM ({sql}) t", {"version": v}).fetchone()[0]
                total += n
                print(f"  {table.name:28} {n:>8}")
                if not copy or not n:
                    continue
                cols = ", ".join(f'"{c.name}"' for c in columns(table))
                with src.cursor().copy(f"COPY ({sql}) TO STDOUT", {"version": v}) as out, \
                        dst.cursor().copy(f'COPY "{table.name}" ({cols}) FROM STDIN') as into:  # fmt: skip
                    for block in out:
                        into.write(block)
            if copy:
                _reset_sequences(dst, tables_in_load_order())
                _check(src, dst, v)
        if copy:
            size = dst.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
            print(f"copied {total} rows; target database size {size}")
        else:
            print(f"{total} rows would be copied (dry run: add --copy)")
    return total


def _has_table(conn: psycopg.Connection, name: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{name}",)).fetchone()[0]


def _reset_sequences(dst: psycopg.Connection, tables: list[Table]) -> None:
    for t in tables:
        for c in t.primary_key.columns:
            seq = dst.execute("SELECT pg_get_serial_sequence(%s, %s)", (t.name, c.name)).fetchone()[0]
            if seq:
                dst.execute(
                    f'SELECT setval(%s, COALESCE((SELECT max("{c.name}") FROM "{t.name}"), 0) + 1, false)', (seq,)
                )


def _check(src: psycopg.Connection, dst: psycopg.Connection, v: int) -> None:
    """Every copied table matches the source's filtered count; every NEVER table is empty (roles: as migrated)."""
    for t in tables_in_load_order():
        want = src.execute(f"SELECT count(*) FROM ({select_sql(t)}) x", {"version": v}).fetchone()[0]
        got = dst.execute(f'SELECT count(*) FROM "{t.name}"').fetchone()[0]
        if want != got:
            raise SystemExit(f"{t.name}: copied {got} rows, expected {want}")
    for name in sorted(NEVER - {"roles"}):
        if _has_table(dst, name) and dst.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]:
            raise SystemExit(f"{name} is not empty in the target: this export never writes it; check the target")


def main(argv: list[str] | None = None) -> None:
    from app.config import get_settings

    ap = argparse.ArgumentParser(prog="python -m app.demo_export", description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True, help="the demo database URL (Neon), schema already migrated")
    ap.add_argument("--source", help="default: DATABASE_URL (your local database)")
    ap.add_argument("--version", type=int, help="dataset version id (default: the published one)")
    ap.add_argument("--copy", action="store_true", help="copy (without it: a dry run that only counts)")
    a = ap.parse_args(argv)
    source = a.source or get_settings().database_url
    if (
        make_url(libpq(source)).host == make_url(libpq(a.target)).host
        and make_url(libpq(source)).database == make_url(libpq(a.target)).database
    ):
        sys.exit("source and target are the same database")
    run(source, a.target, a.version, a.copy)


if __name__ == "__main__":
    main()
