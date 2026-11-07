"""Phase 5.6: the CI eval gate (app.datasets.ci_eval) uses the publish gate's rules."""

import json
from types import SimpleNamespace

import pytest

from app.datasets import ci_eval
from app.datasets.evaluation import is_danger_case


def report(danger_missed: int, top3_hits: int, scope: str = "quick") -> dict:
    """800 danger cases and 100 ranked cases, keyed as evaluation.case_key would."""
    results = {f"safety|F{i:03}|high|says x": {"type": "safety", "category": "brakes", "label": f"rule {i}",
                                               "alert_ok": i >= danger_missed} for i in range(800)}  # fmt: skip
    results |= {f"ft-{i}": {"type": "free_text", "category": "ac", "label": f"case {i}", "hit1": i < top3_hits,
                            "hit3": i < top3_hits} for i in range(100)}  # fmt: skip
    return {"scope": scope, "overall": {}, "results": results}


def write(tmp_path, name: str, data: dict):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize(
    ("missed", "top3", "ok"),
    [
        (9, 75, True),  # same as main
        (8, 75, True),  # fewer danger cases missed
        (9, 72, True),  # top-3 down 3 points: allowed
        (10, 75, False),  # one more danger case missed
        (9, 71, False),  # top-3 down 4 points
    ],
)
def test_gate_matches_the_publish_rules(tmp_path, missed, top3, ok):
    base = write(tmp_path, "main.json", report(9, 75))
    cand = write(tmp_path, "pr.json", report(missed, top3))
    summary = tmp_path / "summary.md"
    assert ci_eval.gate(cand, base, summary) is ok
    text = summary.read_text()
    assert "800 danger cases" in text
    assert ("**Passed.**" in text) is ok


def test_no_baseline_yet_passes_with_a_note(tmp_path):
    cand = write(tmp_path, "pr.json", report(9, 75))
    summary = tmp_path / "s.md"
    assert ci_eval.gate(cand, tmp_path / "missing.json", summary)
    assert "No baseline report" in summary.read_text()


def test_cli_exit_code(tmp_path):
    base = write(tmp_path, "main.json", report(9, 75))
    bad = write(tmp_path, "pr.json", report(12, 75))
    with pytest.raises(SystemExit) as e:
        ci_eval.main(["gate", "--candidate", str(bad), "--baseline", str(base)])
    assert e.value.code == 1


def test_quick_scope_keeps_every_danger_case():
    assert ci_eval.SCOPES["quick"]["danger_all"] and ci_eval.SCOPES["quick"]["split"] == "test"
    assert ci_eval.SCOPES["full"]["split"] == "all"
    assert is_danger_case(SimpleNamespace(expected_alert={"risk": "high"}))
    assert not is_danger_case(SimpleNamespace(expected_alert={"none": True}))
    assert not is_danger_case(SimpleNamespace(expected_alert=None))
