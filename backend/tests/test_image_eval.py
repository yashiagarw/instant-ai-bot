"""data/eval/run_image_eval.py: the manifest format, zero photos, scoring and rates (with a fake reader)."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from app.vision.models import AnalysisMode, FindingStatus
from tests.test_uploads_imaging import photo

SCRIPT = Path(__file__).resolve().parents[2] / "data" / "eval" / "run_image_eval.py"
spec = importlib.util.spec_from_file_location("run_image_eval", SCRIPT)
ev = importlib.util.module_from_spec(spec)
sys.modules["run_image_eval"] = ev  # dataclasses look their module up here
spec.loader.exec_module(ev)


def test_the_shipped_manifest_is_empty_and_the_script_handles_it(capsys):
    assert ev.load_manifest(ev.MANIFEST) == []
    assert ev.main([]) == 0
    assert "nothing to evaluate" in capsys.readouterr().out
    example = ev.load_manifest(ev.IMAGES_DIR / "manifest.example.yaml")
    assert [i.mode for i in example][:3] == [
        AnalysisMode.warning_light,
        AnalysisMode.warning_light,
        AnalysisMode.damage,
    ]


def test_scoring_and_rates(tmp_path):
    (tmp_path / "photos").mkdir()
    for name in ("oil.jpg", "belt.jpg", "blur.jpg", "dash.jpg"):
        (tmp_path / "photos" / name).write_bytes(photo("JPEG", size=(300, 200)))
    (tmp_path / "manifest.yaml").write_text(
        """photos:
  - {file: photos/oil.jpg, mode: warning_light, expect: [oil_pressure]}
  - {file: photos/dash.jpg, mode: warning_light, expect: [oil_pressure]}
  - {file: photos/belt.jpg, mode: damage, expect: [belt_cracked]}
  - {file: photos/blur.jpg, mode: damage, expect: []}
  - {file: photos/gone.jpg, mode: damage, expect: [oil_leak]}
"""
    )
    answers = iter(
        [
            (FindingStatus.found, [{"code": "oil_pressure", "confidence": 0.9}]),
            (FindingStatus.found, [{"code": "check_engine", "confidence": 0.8}]),
            (FindingStatus.unclear, []),
            (FindingStatus.unclear, []),
        ]
    )
    seen = []

    def read(mode, labels, jpeg):
        seen.append(jpeg[:2])
        status, labels = next(answers)
        return SimpleNamespace(status=status, labels=labels)

    items = ev.load_manifest(tmp_path / "manifest.yaml")
    scored = ev.evaluate(items, tmp_path, read, {m: [] for m in AnalysisMode}, 10_000_000, 2000)
    assert [s.verdict for s in scored] == ["correct", "wrong", "unclear", "correct", "missing"]
    assert seen == [b"\xff\xd8"] * 4  # re-encoded like an upload
    summary = ev.summarise(scored, {"oil_pressure"})
    assert summary["by_mode"]["all"]["correct_rate"] == 0.4
    assert summary["by_mode"]["warning_light"] == {
        "n": 2, "correct": 1, "wrong": 1, "unclear": 0, "missing": 0,
        "correct_rate": 0.5, "wrong_rate": 0.5, "unclear_rate": 0.0,
    }  # fmt: skip
    assert summary["red_light_recall"] == {"n": 2, "found": 1, "rate": 0.5}
