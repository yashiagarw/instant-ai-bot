"""The evaluation harness in data/eval/evalkit (no database: the engine fixture knowledge)."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data" / "eval"))

from evalkit import report as rep  # noqa: E402
from evalkit.cases import (  # noqa: E402
    Case,
    CaseError,
    chip_cases,
    language,
    load_yaml_cases,
    phrase_cases,
    safety_cases,
    typo,
    unlisted_variants,
)
from evalkit.cli import build_cases, evaluate  # noqa: E402
from evalkit.metrics import stats, summarise  # noqa: E402
from evalkit.runner import run_case  # noqa: E402
from evalkit.versions import CURRENT, VersionError, engine_hash, materialise  # noqa: E402

from engine import ENGINE_VERSION, Engine  # noqa: E402
from tests.test_engine import knowledge  # noqa: E402, F401 - fixture

PHRASES = [
    ("brake se squeal awaaz aati hai", 1, "hinglish"),
    ("brake fluid is leaking under the car", 2, "en"),
    ("tyre went completely flat", 4, None),
    ("clutch pedal feels very hard", 7, "en"),
]


# ---------------------------------------------------------------- cases


def test_typos_are_deterministic_small_and_keep_the_first_letter():
    text = "brake fluid is leaking under the car"
    assert typo(text) == typo(text) != text
    changed = [(a, b) for a, b in zip(text.split(), typo(text).split(), strict=True) if a != b]
    assert len(changed) == 1 and changed[0][0][0] == changed[0][1][0]
    assert abs(len(changed[0][0]) - len(changed[0][1])) <= 1
    assert typo("ac ok") == "ac ok"  # no word long enough to change


def test_language_tags():
    assert language("बैटरी फूल गई") == "hi"
    assert language("battery down", "hinglish") == "hinglish"
    assert language("battery is dead") == "en"


def test_phrase_cases_give_free_text_typos_and_overlap(knowledge):  # noqa: F811
    cases = phrase_cases(knowledge, PHRASES, typo_every=2)
    by_type = {}
    for c in cases:
        by_type.setdefault((c.type, c.source), []).append(c)
    assert len(by_type[("free_text", "dataset")]) == 4
    assert {c.lang for c in by_type[("free_text", "dataset")]} == {"hinglish", "en"}
    typos = by_type[("free_text", "synthetic")]
    assert typos and all(c.lang == "typo" and c.note.startswith("typo of held-out phrase") for c in typos)
    # brakes and clutch share the "Brakes & clutch" tile: their phrases also start from that tile.
    overlap = by_type[("overlap", "dataset")]
    assert {c.category for c in overlap} == {"brakes", "clutch"} and {c.group for c in overlap} == {"brakes_clutch"}
    assert all(c.simulate for c in cases)
    assert len({c.id for c in cases}) == len(cases)  # stable, unique ids


def test_chip_safety_and_unlisted_cases(knowledge):  # noqa: F811
    chips = chip_cases(knowledge)
    assert chips and all(c.type == "chips" and not c.text and c.simulate for c in chips)
    assert "chips-F09-ST-01" not in {c.id for c in chips}  # fast_track category: no chip case
    safety = safety_cases(knowledge, knowledge.rules)
    rule1 = [c for c in safety if c.expected_alert["rule_id"] == 1]
    assert {(c.answers and c.answers[0][1]) or c.text for c in rule1} == {111, "brake fail"}
    unl = unlisted_variants(phrase_cases(knowledge, PHRASES, typo_every=0), every=2)
    assert len(unl) == 4
    assert {(c.vehicle["segment"], c.expected_coverage[0]) for c in unl} == {
        (None, "general_guidance"),
        ("mid", "segment_estimate"),
    }


def write_yaml(path: Path, text: str) -> Path:
    path.mkdir(exist_ok=True)
    (path / "cases.yaml").write_text(text, encoding="utf-8")
    return path


def test_yaml_cases_resolve_questions_and_defaults(knowledge, tmp_path):  # noqa: F811
    d = write_yaml(
        tmp_path / "c",
        """
- id: chip
  group: tyres
  answers: [{question: "What is the brake problem?", option: "Leak"}]
  expected: F11-BR-02
- {id: hindi, text: "ब्रेक से तेल रिस रहा है", expected: [F11-BR-02, F11-BR-03]}
- id: unl
  type: unlisted
  vehicle: {listed: false}
  text: brake leak
  expected: F11-BR-02
  expected_coverage: general_guidance
- {id: alarm, type: safety, text: brake fail, expected_alert: high}
- {id: quiet, type: safety, text: tyre pressure check, expected_alert: none}
""",
    )
    cases = {c.id: c for c in load_yaml_cases(knowledge, d)}
    assert cases["cases:chip"].answers == [(100, 102)] and not cases["cases:chip"].simulate
    assert cases["cases:chip"].type == "chips" and cases["cases:chip"].source == "synthetic"
    assert cases["cases:hindi"].lang == "hi" and cases["cases:hindi"].simulate
    assert cases["cases:unl"].expected_coverage == ["general_guidance"]
    assert cases["cases:alarm"].expected_alert == {"risk": "high"} and not cases["cases:alarm"].simulate
    assert cases["cases:quiet"].expected_alert == {"none": True}


@pytest.mark.parametrize(
    "text, message",
    [
        ("- {id: a, expected: F99-XX-01}", "unknown expected fault"),
        ("- {id: a, text: x}", "needs `expected`"),
        ("- {id: a, type: chat, expected: F11-BR-01}", "type must be"),
        ("- {id: a, source: llm, expected: F11-BR-01}", "source must be"),
        ("- {id: a, expected: F11-BR-01, expected_coverage: exact}", "unknown coverage"),
        ("- {id: a, answers: [{question: Nope, option: x}], expected: F11-BR-01}", "no approved question"),
        ("- {id: a, expected: F11-BR-01}\n- {id: a, expected: F11-BR-02}", "duplicate case id"),
    ],
)
def test_yaml_case_errors(knowledge, tmp_path, text, message):  # noqa: F811
    with pytest.raises(CaseError, match=message):
        load_yaml_cases(knowledge, write_yaml(tmp_path / "c", text))


# ---------------------------------------------------------------- running and metrics


def test_run_case_records_hits_alerts_coverage_and_questions(knowledge):  # noqa: F811
    engine = Engine(knowledge)
    chip = run_case(
        engine, Case("c", "chips", "generated", "brakes", ["F11-BR-02"], group="brakes_clutch", simulate=True)
    )
    assert chip["hit1"] and chip["hit3"] and chip["questions"] >= 1 and chip["got"][0] == "F11-BR-02"
    # Either of several expected faults counts; the simulated customer follows the first one.
    either = run_case(
        engine,
        Case("e", "chips", "synthetic", "brakes", ["F11-BR-03", "F11-BR-01"], group="brakes_clutch", simulate=True),
    )
    assert either["hit3"]
    alarm = run_case(
        engine, Case("s", "safety", "synthetic", "brakes", text="brake fail", expected_alert={"risk": "high"})
    )
    assert alarm["alert_ok"] is True
    rule = run_case(
        engine,
        Case(
            "r",
            "safety",
            "generated",
            "brakes",
            category_pick="brakes",
            answers=[(110, 111)],
            expected_alert={"rule_id": 1, "risk": "high"},
        ),
    )
    assert rule["alert_ok"] is True
    quiet = run_case(
        engine, Case("q", "safety", "synthetic", "tyre", text="tyre goes soft again", expected_alert={"none": True})
    )
    assert quiet["false_alarm"] is False
    unl = run_case(
        engine,
        Case(
            "u",
            "unlisted",
            "synthetic",
            "tyre",
            ["F04-TY-03"],
            vehicle={"listed": False, "segment": None},
            text="tyre puncture flat",
            simulate=True,
            expected_coverage=["general_guidance"],
        ),
    )
    assert unl["coverage"] == "general_guidance" and unl["coverage_ok"]
    assert unl["input"]["vehicle"] == {"listed": False, "segment": None}


def r(**kw):
    base = {"type": "free_text", "source": "dataset", "category": "tyre", "questions": 2, "lang": "en"}
    return {**base, **kw}


def test_metrics():
    results = [
        r(hit1=True, hit3=True, questions=4),
        r(hit1=False, hit3=True, questions=2, flow_rule=True, flow_rule_fired=True),
        r(hit1=False, hit3=False, questions=0, flow_rule=True, flow_rule_fired=False, lang="hi"),
        r(type="safety", category="brakes", alert_ok=True, questions=0),
        r(type="safety", category="brakes", alert_ok=False, questions=0),
        r(type="safety", category="brakes", false_alarm=True, questions=0),
        r(type="unlisted", hit1=True, hit3=True, coverage_ok=True, questions=3),
    ]
    s = stats(results)
    assert (s["n"], s["ranked_n"], s["top1"], s["top3"]) == (7, 4, 0.5, 0.75)
    assert s["avg_questions"] == 2.25  # conversations only, safety cases excluded
    assert (s["safety_n"], s["safety_recall"], s["false_alarms"]) == (2, 0.5, 1.0)
    assert (s["flow_safety_n"], s["flow_safety_recall"], s["coverage_correct"]) == (2, 0.5, 1.0)
    summary = summarise(results)
    assert summary["phase1"]["n"] == 7 and summary["other_categories"]["n"] == 0
    assert set(summary["by_language"]) == {"en", "hi"} and summary["by_category"]["brakes"]["safety_n"] == 2
    assert stats([])["top1"] is None


# ---------------------------------------------------------------- reports and compare


def fake_report(label: str, results: list[dict]) -> dict:
    return {
        "meta": {
            "created_at": "2026-10-24T05:00:00+00:00",
            "stamp": rep.timestamp(datetime(2026, 10, 24, 5, tzinfo=UTC)),
            "engine_label": label,
            "engine_version": "1.0.0",
            "engine_hash": "abc",
            "git_commit": "fc2480f",
            "dataset_version_id": 36,
            "embeddings": False,
            "cases": len(results),
            "cases_by_source": {"dataset": len(results)},
        },
        "summary": summarise(results),
        "results": results,
    }


def test_report_files_are_timestamped_markdown_and_json(tmp_path):
    report = fake_report("current", [r(id="a", expected=["F04-TY-03"], got=["F04-TY-01"], hit1=False, hit3=False)])
    jpath, mpath = rep.write(report, tmp_path)
    assert jpath.name == "20261024-050000Z_eval_current.json" and mpath.suffix == ".md"
    assert json.loads(jpath.read_text())["summary"]["overall"]["top1"] == 0.0
    md = mpath.read_text()
    assert "# Engine evaluation: current" in md and "| All cases | 1 |" in md
    assert "`a`: expected F04-TY-03, got F04-TY-01" in md and "Synthetic cases" in md


def test_compare_lists_cases_that_changed(tmp_path):
    base = fake_report("740ea77", [
        r(id="a", got=["X"], hit1=False, hit3=False),
        r(id="b", got=["Y"], hit1=True, hit3=True),
        r(id="c", got=["Z"], hit1=True, hit3=True),
        r(id="gone", got=[], hit1=False, hit3=False),
    ])  # fmt: skip
    cand = fake_report("current", [
        r(id="a", got=["Y"], hit1=True, hit3=True),
        r(id="b", got=["X"], hit1=False, hit3=True),
        r(id="c", got=["Z"], hit1=True, hit3=True, questions=5),
        r(id="new", got=[], hit1=False, hit3=False),
    ])  # fmt: skip
    cmp = rep.compare(base, cand)
    verdicts = {ch["id"]: ch["verdict"] for ch in cmp["changes"]}
    assert verdicts == {"a": "better", "b": "worse", "c": "changed"}
    assert cmp["only_in_base"] == ["gone"] and cmp["only_in_candidate"] == ["new"]
    assert next(ch for ch in cmp["changes"] if ch["id"] == "c")["diff"] == {"questions": (2, 5)}
    _, mpath = rep.write(cmp, tmp_path, kind="compare")
    md = mpath.read_text()
    assert mpath.name.endswith("_compare_740ea77-vs-current.md")
    assert "3 cases changed: better 1, changed 1, worse 1." in md and "`b` (tyre): hit1: True → False" in md


# ---------------------------------------------------------------- engine versions and a full run


def test_engine_versions(tmp_path):
    assert materialise(CURRENT) is None
    here = ROOT / "backend"
    assert materialise(str(here)) == here.resolve()
    assert materialise(str(here / "engine")) == here.resolve()
    extracted = materialise("HEAD", tmp_path)
    assert (extracted / "engine" / "core.py").is_file() and not (extracted / "app").exists()
    assert engine_hash(extracted / "engine") == engine_hash(extracted / "engine")
    with pytest.raises(VersionError):
        materialise("no-such-ref-xyz", tmp_path)


def test_full_run_on_fixture_knowledge(knowledge, tmp_path):  # noqa: F811
    d = write_yaml(tmp_path / "c", "- {id: alarm, type: safety, text: brake fail, expected_alert: high}")
    cases = build_cases(knowledge, PHRASES, d)
    assert {c.type for c in cases} == {"free_text", "overlap", "chips", "safety", "unlisted"}
    report = evaluate(knowledge, cases, label="current", embeddings=False)
    assert report["meta"]["cases"] == len(cases) == len(report["results"])
    assert report["meta"]["engine_version"] == ENGINE_VERSION and len(report["meta"]["engine_hash"]) == 10
    assert report["summary"]["by_type"]["safety"]["safety_recall"] is not None
    jpath, mpath = rep.write(report, tmp_path / "reports")
    assert jpath.exists() and mpath.exists()


def test_dev_test_split_keeps_variants_together_and_people_written_cases_in_test(knowledge):  # noqa: F811
    from evalkit.cases import split_of

    cases = phrase_cases(knowledge, PHRASES, typo_every=1) + chip_cases(knowledge)
    by_phrase: dict[str, set[str]] = {}
    for c in cases:
        by_phrase.setdefault(c.split_key, set()).add(split_of(c))
    assert all(len(sides) == 1 for sides in by_phrase.values())  # free text, typo and overlap of a phrase together
    assert {split_of(c) for c in cases} <= {"dev", "test"}
    written = Case("synthetic_hindi:x", "free_text", "synthetic", "tyre", ["F04-TY-03"], text="टायर")
    assert split_of(written) == "test"  # never tuned on
    assert split_of(cases[0]) == split_of(cases[0])  # stable


# ---------------------------------------------------------------- LLM extraction (run --extraction llm)


def test_extract_hook_adds_symptom_ids_once_per_text_case(knowledge):  # noqa: F811
    import copy

    from engine import types as et

    k = copy.deepcopy(knowledge)
    k.texts.append(et.TextEntry(3, "Steering wheel shakes when braking", "symptom", id=501))
    engine = Engine(k)
    seen = []

    def extract(eng, request):
        seen.append(request.text)
        return [501]

    case = Case(
        id="x", type="free_text", source="synthetic", text="steering shakes", category="brakes", expected=["F11-BR-03"]
    )
    out = run_case(engine, case, extract)
    assert seen == ["steering shakes"] and out["got"][0] == "F11-BR-03"
    run_case(engine, Case(id="y", type="chips", source="synthetic", category="brakes", group="brakes_clutch"), extract)
    assert seen == ["steering shakes"]  # no text: no extraction


def test_llm_extraction_with_provider_none_is_the_fallback(knowledge, monkeypatch):  # noqa: F811
    """LLM_PROVIDER=none: --extraction llm gives the same results as no extraction and makes no call."""
    from evalkit.cli import make_extract

    from app.config import Settings

    monkeypatch.setattr("app.config.get_settings", lambda: Settings(_env_file=None))
    extract, meta = make_extract("llm")
    cases = build_cases(knowledge, PHRASES, ROOT / "data" / "eval" / "cases" / "missing")
    engine = Engine(knowledge)
    assert [run_case(engine, c, extract) for c in cases] == [run_case(engine, c) for c in cases]
    m = meta()
    assert m["extraction"].startswith("llm (fallback") and m["llm_provider"] == "none"
    assert m["llm_usage"]["calls"] == 0 and m["llm_usage"]["cost_usd_estimate"] == 0
    assert rep._extraction_label(m).endswith("estimated $0")
