"""Reviewed extra customer phrases (data/review/phrases) and the question-file rules from the accuracy round."""

import dataclasses
from collections import defaultdict
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from app.knowledge.importer.config import load_config
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.importer.run import run_import
from app.knowledge.models import CustomerPhrase
from app.knowledge.phrases import PHRASES_DIR, PhraseFileError, draft_spellings, load, read_all, validate
from engine.safety import MAX_FAULT_ALERTS
from tests.importer_fixtures import fault, make_workbook

QUESTIONS = Path(__file__).resolve().parents[2] / "data" / "review" / "questions"
HUMAN_REVIEWED = {"battery", "tyre"}  # reviewed by a person: left as they approved them


@pytest.fixture
def battery_db(db_session, tmp_path):
    rows = [
        fault("BT-01", "BATTERY ISSUE", "Weak battery", customer_phrases='1. "battery weak hai, engine slow"'),
        fault("BT-02", "BATTERY ISSUE", "Dead battery", customer_phrases='1. "battery dead"\n2. "engine nahi chala"'),
    ]
    path = make_workbook(tmp_path / "battery.xlsx", 4, rows)
    cfg = load_config()
    cfg.files = {8: dataclasses.replace(cfg.files[8], path=path)}
    cfg.review_dir, cfg.media_dir = tmp_path / "review", tmp_path / "media"
    run_import(db_session, cfg, [cfg.files[8]], all_files=True, embedder=FakeEmbedder(), log=lambda _: None)
    return db_session


def doc(*phrases):
    return [(Path("x.yaml"), {"phrases": list(phrases)})]


def entry(text, fault="F08-BT-01", status="approved", language="hinglish"):
    return {"fault": fault, "status": status, "language": language, "text": text}


def test_validate_rejects_bad_entries():
    keys = {"F08-BT-01"}
    validate(doc(entry("battery kamzor hai")), keys)
    for bad in (
        doc(entry("x", fault="F99-ZZ-01")),
        doc(entry("battery kamzor hai", language="fr")),
        doc(entry("  ")),
        doc(entry("same text"), entry("Same text")),
    ):
        with pytest.raises(PhraseFileError):
            validate(bad, keys)


def test_load_replaces_drafted_phrases_and_skips_drafts(battery_db):
    report = load(battery_db, doc(entry("betri kamzor hai"), entry("not checked yet", status="draft")))
    assert (report.loaded, len(report.skipped)) == (1, 1)
    load(battery_db, doc(entry("betri kamzor hai"), entry("betri down", fault="F08-BT-02")))  # re-run replaces
    drafted = battery_db.scalars(select(CustomerPhrase).where(CustomerPhrase.source == "drafted")).all()
    assert sorted(p.text for p in drafted) == ["betri down", "betri kamzor hai"]
    assert all(p.status == "approved" and not p.held_out and p.is_synthetic for p in drafted)


def test_spelling_variants_follow_the_fault_and_never_copy_a_held_out_phrase(battery_db, tmp_path):
    (tmp_path / "spelling_variants.yaml").write_text(
        "status: approved\nreviewed_by: test\nvariants:\n  battery: [betri]\n  engine: [injan]\n", encoding="utf-8"
    )
    held = battery_db.scalars(select(CustomerPhrase).where(CustomerPhrase.held_out.is_(True))).all()
    for p in held:  # make every held-out phrase one that a variant would produce
        p.text = p.text.lower().replace("battery", "betri").replace("engine", "injan")
    battery_db.flush()
    path, n = draft_spellings(battery_db, tmp_path)
    phrases = yaml.safe_load(path.read_text(encoding="utf-8"))["phrases"]
    assert n == len(phrases) > 0
    held_texts = {p.text.lower() for p in held}
    assert not any(p["text"].lower() in held_texts for p in phrases)
    for p in phrases:
        assert ("betri" in p["text"] and "battery" in p["why"]) or ("injan" in p["text"] and "engine" in p["why"])


def test_repository_phrase_files_are_valid_and_marked_for_review():
    docs = read_all(PHRASES_DIR)
    assert docs and all(d.get("reviewed_by") == "claude_code (auto, pending mechanic sign-off)" for _, d in docs)
    keys = {p["fault"] for _, d in docs for p in d.get("phrases") or []}
    validate(docs, keys)


def test_question_files_keep_danger_phrases_within_the_alert_cap():
    """A danger phrase on more faults than the app can show alerts for would leave some rules unable to fire."""
    for path in sorted(QUESTIONS.glob("*.yaml")):
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        if d["category"] in HUMAN_REVIEWED:
            continue
        by_phrase = defaultdict(list)
        for key, f in (d.get("faults") or {}).items():
            if f.get("status") == "approved":
                for p in f.get("danger_phrases") or []:
                    by_phrase[p.lower().strip()].append(key)
        over = {p: k for p, k in by_phrase.items() if len(k) > MAX_FAULT_ALERTS}
        assert not over, f"{path.name}: {over}"


def test_separating_questions_name_their_pair_and_reviewer():
    found = 0
    for path in sorted(QUESTIONS.glob("*.yaml")):
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        for q in d["questions"]:
            if "-sep-" not in q["id"]:
                continue
            found += 1
            a, b = q["separates"]
            assert a in d["faults"] and b in d["faults"] and q["reviewed_by"].startswith("claude_code (auto")
            effects = {e["fault"] for o in q["options"] for e in o["effects"]}
            assert {a, b} <= effects
            assert sum(1 for o in q["options"] if o.get("not_sure")) == 1
    assert found >= 10


def test_hinglish_smoke_phrases_name_where_the_smoke_is():
    """Black / white exhaust smoke ("kala dhuan") is not an emergency: a smoke danger phrase must say where it is."""
    for path in sorted(QUESTIONS.glob("*.yaml")):
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key, f in (d.get("faults") or {}).items():
            for p in f.get("danger_phrases") or []:
                words = p.lower().split()
                if any(w.startswith("dhua") for w in words):
                    assert len(words) > 1 and words[0] not in ("kala", "kaala", "neela"), f"{path.name} {key}: {p}"
