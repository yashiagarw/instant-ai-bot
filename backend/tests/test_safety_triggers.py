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


SMOKE_RULES = ["F12 SAFETY_AND_TOWING_RULES r87", "F18 SAFETY_AND_TOWING_RULES r68"]


def repo_rule(ref: str) -> EngineRule:
    entry = read()["rules"][ref]
    return EngineRule(id=1, scope="global", risk="high", stop_trigger=ref, phrases=_flat(entry["phrases"]))


@pytest.mark.parametrize("ref", list(read()["rules"]))
def test_repository_global_rules_ignore_exhaust_smoke(ref):
    rule = repo_rule(ref)
    assert "smoke" not in rule.phrases
    for text in NOT_EMERGENCIES:
        assert not fired(rule, text), text


@pytest.mark.parametrize("ref", SMOKE_RULES)
def test_repository_smoke_rules_fire_on_bonnet_smoke(ref):
    hits = [t for t in EMERGENCIES if fired(repo_rule(ref), t)]
    assert {"smoke from the bonnet", "smoke coming from the wires", "bonnet se dhuan aa raha"} <= set(hits)


# 7 Nov 2026: danger cases the eval missed, and look-alikes that are not emergencies. Hindi is read through its
# Hinglish form, as the engine does (engine.hindi.expand).
def fired_expanded(rule: EngineRule, text: str) -> bool:
    from engine.hindi import expand

    return fired(rule, expand(text))


@pytest.mark.parametrize(
    ("ref", "text", "fires"),
    [
        ("F18 SAFETY_AND_TOWING_RULES r68", "पेट्रोल की तेज़ गंध आ रही है और धुआं भी", True),
        ("F18 SAFETY_AND_TOWING_RULES r68", "strong petrol smell and smoke from the car", True),
        ("F18 SAFETY_AND_TOWING_RULES r68", "petrol ki smell aati hai thodi", False),
        ("F18 SAFETY_AND_TOWING_RULES r68", "petrol car se kala dhuan aata hai", False),
        ("F18 SAFETY_AND_TOWING_RULES r70", "car paani mein doob gayi engine band ho gaya", True),
        ("F18 SAFETY_AND_TOWING_RULES r70", "गाड़ी पानी में डूब गई इंजन बंद हो गया", True),
        ("F18 SAFETY_AND_TOWING_RULES r70", "engine stopped in water on the flooded road", True),
        ("F18 SAFETY_AND_TOWING_RULES r70", "AC ka paani gaadi ke neeche, engine band karne ke baad", False),
        # Under water earlier, engine not said to have stopped: the flood faults' own rules handle it.
        ("F18 SAFETY_AND_TOWING_RULES r70", "Gaadi paani me doob gayi thi", False),
        ("F18 SAFETY_AND_TOWING_RULES r70", "wiper ka paani nahi aata", False),
    ],
)
def test_new_global_phrases(ref, text, fires):
    assert fired_expanded(repo_rule(ref), text) is fires


def brake_failure_rule() -> EngineRule:
    doc = yaml.safe_load((QUESTIONS / "brakes.yaml").read_text(encoding="utf-8"))
    phrases = doc["faults"]["F11-BR-04"]["danger_phrases"]
    return EngineRule(id=2, scope="global", risk="high", stop_trigger="brake failure", phrases=phrases)


@pytest.mark.parametrize(
    ("text", "fires"),
    [("ब्रेक फेल हो गए हैं", True), ("brakes failed on the highway", True), ("brake fail ho gaya", True),
     ("brake makes noise when I press it", False), ("brake light stays on", False)],
)  # fmt: skip
def test_brake_failure_phrases(text, fires):
    assert fired_expanded(brake_failure_rule(), text) is fires


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


def test_placeholder_roadside_actions_are_cleared_and_kept_in_details(db_session, global_rule):
    """ "No - None." is not advice: cleared on apply (the sheet value kept), so alerts are not merged by it."""
    global_rule.roadside_action = "No - None."
    other = SafetyRule(
        dataset_version_id=global_rule.dataset_version_id, scope="global", kind="general", risk_level="high",
        stop_driving_trigger="Something else", roadside_action="Real advice.", towing_recommendation="",
        triggers={}, status="active_pending_signoff", source="sheet", source_ref="F12 SAFETY_AND_TOWING_RULES r99",
    )  # fmt: skip
    db_session.add(other)
    db_session.flush()
    doc = {"placeholder_roadside_actions": ["no - none."], "rules": {}}
    assert apply_triggers(db_session, doc) == 0
    db_session.refresh(global_rule)
    db_session.refresh(other)
    assert global_rule.roadside_action == "" and global_rule.details["sheet_roadside_action"] == "No - None."
    assert other.roadside_action == "Real advice." and "sheet_roadside_action" not in (other.details or {})
    assert apply_triggers(db_session, doc) == 0  # again: nothing left to clear, the sheet value stays
    assert global_rule.details["sheet_roadside_action"] == "No - None."


def test_rules_with_their_own_advice_are_no_longer_merged():
    """Two rules that had only the placeholder in common now show as two alerts."""
    a = EngineRule(id=1, scope="global", risk="high", stop_trigger="Switch off the engine.", phrases=["milky oil"])
    b = EngineRule(id=2, scope="global", risk="medium", stop_trigger="Stop driving long distances.",
                   phrases=["milky oil"])  # fmt: skip
    alerts = safety.evaluate([a, b], "milky oil", set(), set(), {}, {}, {})
    assert [x.rule_id for x in alerts] == [1, 2]
