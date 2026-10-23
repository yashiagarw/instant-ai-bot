"""Reviewed duplicate merges: validation, merged_into links (no rows deleted), folding in the engine snapshot."""

import dataclasses

import pytest
from sqlalchemy import func, select

from app.diagnosis.knowledge import load_knowledge
from app.knowledge.importer.config import load_config
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.importer.run import run_import
from app.knowledge.merges import MERGES_PATH, MergeFileError, apply_merges, read, validate
from app.knowledge.models import Fault, FaultLink
from tests.importer_fixtures import fault, make_workbook

DOC = {"decided_by": "test", "merge": [{"canonical": "F08-BT-01", "aliases": ["F08-BT-02"], "reason": "same"}]}


@pytest.fixture
def battery_db(db_session, tmp_path):
    rows = [fault(f"BT-0{i}", "BATTERY ISSUE", f"Battery fault {i}") for i in (1, 2, 3)]
    path = make_workbook(tmp_path / "battery.xlsx", 4, rows)
    cfg = load_config()
    cfg.files = {8: dataclasses.replace(cfg.files[8], path=path)}
    cfg.review_dir, cfg.media_dir = tmp_path / "review", tmp_path / "media"
    run_import(db_session, cfg, [cfg.files[8]], all_files=True, embedder=FakeEmbedder(), log=lambda _: None)
    return db_session


def test_validate_rejects_unknown_self_and_conflicting_merges():
    keys = {"A", "B", "C"}
    assert validate({"merge": [{"canonical": "A", "aliases": ["B", "C"]}]}, keys) == [("B", "A", ""), ("C", "A", "")]
    for bad in (
        {"merge": [{"canonical": "Z", "aliases": ["A"]}]},
        {"merge": [{"canonical": "A", "aliases": ["A"]}]},
        {"merge": [{"canonical": "A", "aliases": ["B"]}, {"canonical": "C", "aliases": ["B"]}]},
        {"merge": [{"canonical": "A", "aliases": ["B"]}, {"canonical": "B", "aliases": ["C"]}]},
    ):
        with pytest.raises(MergeFileError):
            validate(bad, keys)


def test_apply_writes_links_keeps_rows_and_is_idempotent(battery_db):
    before = battery_db.scalar(select(func.count()).select_from(Fault))
    assert apply_merges(battery_db, DOC).links == 1
    assert apply_merges(battery_db, DOC).links == 1  # replaces, does not duplicate
    links = battery_db.scalars(select(FaultLink).where(FaultLink.relation == "merged_into")).all()
    assert len(links) == 1 and links[0].reviewed and "same" in links[0].note
    assert battery_db.scalar(select(func.count()).select_from(Fault)) == before  # no source rows deleted


def test_loader_folds_same_category_alias(battery_db):
    apply_merges(battery_db, DOC)
    k = load_knowledge(battery_db)
    keys = {f.key for f in k.faults.values()}
    assert keys == {"F08-BT-01", "F08-BT-03"}
    canonical = next(f for f in k.faults.values() if f.key == "F08-BT-01")
    assert canonical.alias_keys == ["F08-BT-02"] and len(k.alias_of) == 1
    assert k.canonical(next(iter(k.alias_of))) == canonical.id


def test_repository_merges_file_is_valid():
    doc = read(MERGES_PATH)
    triples = validate(doc, {k for g in doc["merge"] for k in [g["canonical"], *g["aliases"]]})
    assert len(triples) == sum(len(g["aliases"]) for g in doc["merge"])
    assert all(k["reason"] for k in doc["keep_separate"])
