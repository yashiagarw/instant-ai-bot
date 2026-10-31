"""Global emergency rule triggers (data/review/safety_global_triggers.yaml): exhaust smoke is not a fire alert;
smoke from the bonnet or the wires is."""

from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from app.knowledge.models import DatasetVersion, SafetyRule
from app.knowledge.safety_triggers import TRIGGERS_PATH, TriggerFileError, _flat, apply_triggers, read
from engine import safety
from engine.types import SafetyRule as EngineRule

QUESTIONS = Path(__file__).resolve().parents[2] / "data" / "review" / "questions"
NOT_EMERGENCIES = [
    "black smoke from the exhaust",
    "white smoke from exhaust on cold start",
    "diesel gaadi kala dhuan",
    "silencer se kala dhuan",
]
EMERGENCIES = [
    "smoke from the bonnet",
    "smoke coming from the wires",
    "smoke from dashboard",
    "bonnet se dhuan aa raha",
    "car on fire",
    "sparks and burning plastic smell",
]


def fired(rule: EngineRule, text: str) -> bool:
    alerts = safety.evaluate([rule], text, set(), set(), {}, {}, {})
    return any(a.rule_id == rule.id for a in alerts)


@pytest.mark.parametrize("ref", list(read()["rules"]))
def test_repository_global_rules_ignore_exhaust_smoke_and_fire_on_bonnet_smoke(ref):
    entry = read()["rules"][ref]
    rule = EngineRule(id=1, scope="global", risk="high", stop_trigger=ref, phrases=_flat(entry["phrases"]))
    assert "smoke" not in rule.phrases
    for text in NOT_EMERGENCIES:
        assert not fired(rule, text), text
    hits = [t for t in EMERGENCIES if fired(rule, t)]
    assert {"smoke from the bonnet", "smoke coming from the wires", "bonnet se dhuan aa raha"} <= set(hits)


def test_question_files_have_no_bare_smoke_danger_phrase():
    for path in sorted(QUESTIONS.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key, f in (doc.get("faults") or {}).items():
            bare = [
                p
                for p in f.get("danger_phrases") or []
                if p.lower().strip() in ("smoke", "heavy smoke", "visible smoke")
            ]
            assert not bare, f"{path.name} {key}: {bare}"


@pytest.fixture
def global_rule(db_session):
    version = DatasetVersion(checksum="x" * 64, status="draft")
    db_session.add(version)
    db_session.flush()
    rule = SafetyRule(
        dataset_version_id=version.id,
        scope="global",
        kind="general",
        risk_level="high",
        stop_driving_trigger="If there is smoke, sparks or a burning plastic smell: stop safely",
        roadside_action="Stop and get out.",
        towing_recommendation="Tow.",
        triggers={},
        status="active_pending_signoff",
        source="sheet",
        source_ref="F12 SAFETY_AND_TOWING_RULES r87",
    )
    db_session.add(rule)
    db_session.flush()
    return rule


def test_apply_sets_reviewed_phrases_and_refuses_unknown_rules(db_session, global_rule):
    doc = {
        "reviewed_by": "test",
        "rules": {"F12 SAFETY_AND_TOWING_RULES r87": {"phrases": ["sparks", ["smoke from bonnet"]]}},
    }
    assert apply_triggers(db_session, doc) == 1
    rule = db_session.scalar(select(SafetyRule).where(SafetyRule.id == global_rule.id))
    assert rule.triggers == {"phrases": ["sparks", "smoke from bonnet"], "reviewed_by": "test"}
    with pytest.raises(TriggerFileError):
        apply_triggers(db_session, {"rules": {"F99 nowhere": {"phrases": ["x"]}}})
    with pytest.raises(TriggerFileError):
        apply_triggers(db_session, {"rules": {"F12 SAFETY_AND_TOWING_RULES r87": {"phrases": []}}})


def test_repository_file_is_marked_for_review():
    assert read(TRIGGERS_PATH)["reviewed_by"].startswith("claude_code (auto")
