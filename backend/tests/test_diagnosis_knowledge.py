"""The database -> engine bridge: customer-facing fields only, held-out phrases excluded."""

import dataclasses
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update

from app.diagnosis.knowledge import load_knowledge
from app.knowledge.importer.config import load_config
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.importer.run import run_import
from app.knowledge.models import CustomerPhrase, Fault, SafetyRule
from engine import Engine, Request, Vehicle
from tests.importer_fixtures import fault, make_workbook


@pytest.fixture
def battery_db(db_session, tmp_path):
    rows = [fault(f"BT-0{i}", "BATTERY ISSUE", f"Battery fault {i}") for i in (1, 2, 3)]
    path = make_workbook(tmp_path / "battery.xlsx", 4, rows)
    cfg = load_config()
    cfg.files = {8: dataclasses.replace(cfg.files[8], path=path)}
    cfg.review_dir, cfg.media_dir = tmp_path / "review", tmp_path / "media"
    run_import(db_session, cfg, [cfg.files[8]], all_files=True, embedder=FakeEmbedder(), log=lambda _: None)
    return db_session


def test_loads_faults_costs_and_texts_without_internal_fields(battery_db):
    k = load_knowledge(battery_db)
    assert {f.key for f in k.faults.values()} == {"F08-BT-01", "F08-BT-02", "F08-BT-03"}
    pads = next(f for f in k.faults.values() if f.key == "F08-BT-01")
    assert pads.costs["budget"].total == 600 and set(pads.costs) == {"budget", "mid", "premium"}
    assert pads.repair_time_text == "10-15 minutes" and pads.road_repairable == "yes"
    every_text = [t.text for t in k.texts] + [tip for f in k.faults.values() for tip in f.safety_tips]
    assert any("Clicking sound" in t for t in every_text)
    # MECHANIC TASK / HOW TO REPAIR BY MECHANIC / internal notes never reach the engine.
    assert not any("Load test" in t or "WagonR" in t or t.startswith("Test.") for t in every_text)
    assert k.categories["battery"].source_files == (8,)


def test_held_out_phrases_are_not_indexed(battery_db):
    one = battery_db.scalars(select(CustomerPhrase).order_by(CustomerPhrase.id)).first()
    battery_db.execute(update(CustomerPhrase).where(CustomerPhrase.id == one.id).values(held_out=True))
    k = load_knowledge(battery_db)
    assert (one.fault_id, one.text) not in {(t.fault_id, t.text) for t in k.texts if t.kind == "phrase"}
    assert (one.fault_id, "battery down hai") in {(t.fault_id, t.text) for t in k.texts}


def test_only_live_safety_rules_are_loaded_with_their_triggers(battery_db):
    f = battery_db.scalars(select(Fault)).first()
    now = datetime.now(UTC)
    for status, signed in (("approved", now), ("active_pending_signoff", None), ("draft", None), ("rejected", None)):
        battery_db.add(
            SafetyRule(
                dataset_version_id=f.dataset_version_id,
                scope="fault",
                fault_id=f.id,
                risk_level="high",
                roadside_action=f"rule {status}",
                status=status,
                signed_off_at=signed,
                source="drafted_from_columns",
                triggers={"option_ids": [5], "phrases": ["burning smell"]},
                source_ref="F08 test",
            )
        )
    battery_db.flush()
    rules = {r.roadside_action: r for r in load_knowledge(battery_db).rules}
    assert set(rules) == {"rule approved", "rule active_pending_signoff"}
    live = rules["rule approved"]
    assert live.option_ids == {5} and live.phrases == ["burning smell"] and live.source_file == 8


def test_engine_runs_on_loaded_knowledge(battery_db):
    k = load_knowledge(battery_db)
    r = Engine(k).diagnose(Request(category="battery", text="battery down hai", vehicle=Vehicle(segment="mid")))
    assert r.ranked and r.ranked[0].cost.amount == 800 and r.coverage == "segment_estimate"
    fault_ids = set(battery_db.scalars(select(Fault.id)))
    assert {x.fault_id for x in r.ranked} <= fault_ids
