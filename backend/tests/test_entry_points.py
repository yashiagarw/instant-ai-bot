"""Every way a backend process starts knows every table. Each `python -m app....` command (and the arq worker) is
imported in a fresh Python process, as it would start: if it touched the database it must have registered all
models, resolve every foreign key and configure every mapper. Before app/db.py loaded app.models, entry points that
imported only some model modules crashed at their first query with NoReferencedTableError (dev_seed:
mechanics.staff_user_id -> staff_users; the worker: notifications.user_id -> users). Configuring the mappers is what
their first query or new object does."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import app.models  # noqa: F401
from app.db import Base

BACKEND = Path(__file__).resolve().parents[1]
GUARD = re.compile(r'^if __name__ == "__main__":', re.M)
# Started by other means than `python -m` (arq loads the module by name).
EXTRA = ["app.datasets.worker", "app.main"]
# The commands the README tells people to run: discovery must find them (so it cannot silently find nothing).
MUST_INCLUDE = {
    "app.mechanics.dev_seed",
    "app.admin.cli",
    "app.vehicles.seed",
    "app.knowledge.importer.__main__",
    "app.uploads.storage",
    "app.notify.templates",
    "app.notify.push",
    "app.knowledge.finetune",
    "app.knowledge.embeddings",
    "app.knowledge.questions.__main__",
    "app.parts.__main__",
    "app.mechanics.e2e_seed",
}

PROBE = """
import importlib, json, sys
importlib.import_module(sys.argv[1])
db = sys.modules.get("app.db")
if db is None:  # never touches the database
    print(json.dumps(None))
    raise SystemExit(0)
from sqlalchemy.orm import configure_mappers
configure_mappers()  # what the first query or new object does
tables = db.Base.metadata.tables
[fk.column for t in tables.values() for fk in t.foreign_keys]  # NoReferencedTableError if a table is missing
print(json.dumps(sorted(tables)))
"""


def entry_points() -> list[str]:
    found = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        if GUARD.search(path.read_text(encoding="utf-8")):
            found.append(".".join(path.relative_to(BACKEND).with_suffix("").parts))
    return found + EXTRA


ENTRY_POINTS = entry_points()


def test_discovery_finds_every_command():
    assert MUST_INCLUDE <= set(ENTRY_POINTS), sorted(MUST_INCLUDE - set(ENTRY_POINTS))


def _probe(module: str) -> tuple[str, subprocess.CompletedProcess]:
    out = subprocess.run(
        [sys.executable, "-c", PROBE, module], capture_output=True, text=True, cwd=str(BACKEND), timeout=180
    )
    return module, out


@pytest.fixture(scope="module")
def probes() -> dict[str, subprocess.CompletedProcess]:
    with ThreadPoolExecutor(max_workers=6) as pool:
        return dict(pool.map(_probe, ENTRY_POINTS))


@pytest.mark.parametrize("module", ENTRY_POINTS)
def test_entry_point_loads_every_table(module, probes):
    out = probes[module]
    assert out.returncode == 0, f"{module} failed to import cleanly:\n{out.stderr[-3000:]}"
    tables = json.loads(out.stdout.strip().splitlines()[-1])
    if tables is None:
        return  # this command never touches the database
    assert set(tables) == set(Base.metadata.tables), sorted(set(Base.metadata.tables) - set(tables))
