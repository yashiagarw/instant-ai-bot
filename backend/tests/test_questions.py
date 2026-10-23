"""Question structuring with a fake LLM provider: generation, merging, review files, loading."""

import copy
import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.knowledge.importer.config import load_config
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.importer.run import run_import
from app.knowledge.models import Fault, OptionEffect, Question, QuestionOption, SafetyRule
from app.knowledge.questions import review
from app.knowledge.questions.generate import NOT_SURE, generate_category, merge_groups, raw_questions
from app.knowledge.questions.inputs import category_inputs, target_version
from app.knowledge.questions.llm import AnthropicProvider, FakeProvider, LLMError, ToolRequest, Usage
from app.knowledge.questions.loader import ReviewFileError, load_document
from tests.importer_fixtures import fault, make_workbook

DATASET = {"id": 1, "checksum": "0" * 64}


def make_inputs(code="battery", choices=("Car not starting", "Self slow", "Other"), draft_safety=True, n=3):
    faults = [
        {
            "fault_key": f"F08-BT-0{i}",
            "name": f"Battery fault {i}",
            "description": "d",
            "symptoms": [f"Symptom {i}"],
            "causes": ["cause"],
            "likely_fault": "weak battery",
            "stages": 'STAGE 2 - MAIN PROBLEM\n"What problem are you facing?"\nChoices: a | b',
            "stage2_choices": list(choices),
            "diagnosis_rules": None,
            "safety_precautions": "Do not touch terminals.",
            "towing_conditions": "NO in most cases.",
            "has_sheet_safety_rule": not draft_safety,
        }
        for i in range(1, n + 1)
    ]
    return {
        "category": {"code": code, "name": "Battery", "kind": "diagnose"},
        "faults": faults,
        "file_choices": list(choices),
        "draft_safety": draft_safety,
    }


# ---------------------------------------------------------------- generation


def test_file_choices_are_reused_exactly_as_an_enum():
    provider = FakeProvider()
    doc = generate_category(make_inputs(), provider, DATASET, workers=2, log=lambda _: None)
    fault_calls = [r for r in provider.requests if r.tool_name == "structure_fault"]
    assert len(fault_calls) == 3
    enum = fault_calls[0].schema["properties"]["stage2_choices"]["items"]["enum"]
    assert enum == ["Car not starting", "Self slow", "Other"]
    assert not any(r.tool_name == "propose_stage2_choices" for r in provider.requests)
    main = doc["questions"][0]
    assert main["id"] == "battery-main" and main["choice_source"] == "file"
    assert main["text"] == "What problem are you facing?"
    assert [o["label"] for o in main["options"]] == ["Car not starting", "Self slow", "Other", NOT_SURE]


def test_files_without_choices_get_proposed_choices():
    inputs = make_inputs(code="clutch", choices=())
    for f in inputs["faults"]:
        f["stages"] = "Stage 1 - Vehicle: make, model. Stage 2 - Main complaint: pedal hard"
    provider = FakeProvider()
    doc = generate_category(inputs, provider, DATASET, workers=1, log=lambda _: None)
    assert provider.requests[0].tool_name == "propose_stage2_choices"
    assert doc["questions"][0]["choice_source"] == "proposed"
    assert [o["label"] for o in doc["questions"][0]["options"]][:2] == ["Main problem A", "Main problem B"]


def test_every_question_has_exactly_one_not_sure_without_effects():
    doc = generate_category(make_inputs(), FakeProvider(), DATASET, workers=1, log=lambda _: None)
    for q in doc["questions"]:
        not_sure = [o for o in q["options"] if o.get("not_sure")]
        assert len(not_sure) == 1 and not_sure[0]["label"] == NOT_SURE and not_sure[0]["effects"] == []
        assert sum(o["label"].lower() == "not sure" for o in q["options"]) == 1  # the model's own was dropped
        assert q["status"] == "draft"


def test_same_questions_are_merged_across_faults():
    doc = generate_category(make_inputs(), FakeProvider(), DATASET, workers=1, log=lambda _: None)
    smoke = [q for q in doc["questions"] if "smoke" in q["text"].lower()]
    assert len(smoke) == 1
    assert smoke[0]["source_faults"] == ["F08-BT-01", "F08-BT-02", "F08-BT-03"]
    yes = next(o for o in smoke[0]["options"] if o["label"] == "Yes")
    assert yes["safety_trigger"] is True
    assert doc["faults"]["F08-BT-01"]["safety_trigger_options"] == [{"question": smoke[0]["id"], "option": "Yes"}]


def test_safety_rules_drafted_only_without_a_sheet():
    drafted = generate_category(make_inputs(draft_safety=True), FakeProvider(), DATASET, workers=1, log=lambda _: None)
    assert len(drafted["safety_rules"]) == 3
    rule = drafted["safety_rules"][0]
    assert rule["status"] == "draft" and rule["source_text"]["safety_precautions"] == "Do not touch terminals."

    provider = FakeProvider()
    with_sheet = generate_category(make_inputs(draft_safety=False), provider, DATASET, workers=1, log=lambda _: None)
    assert "safety_rules" not in with_sheet
    schema = next(r for r in provider.requests if r.tool_name == "structure_fault").schema
    assert "safety_rule" not in schema["properties"]


def test_internal_columns_never_reach_the_model():
    provider = FakeProvider()
    inputs = make_inputs()
    inputs["faults"][0]["mechanic_task"] = "SECRET MECHANIC TASK"
    generate_category(inputs, provider, DATASET, workers=1, log=lambda _: None)
    assert all("SECRET" not in r.user_text for r in provider.requests)


def test_failed_fault_is_recorded_not_fatal():
    class Flaky(FakeProvider):
        def call(self, request):
            if request.tool_name == "structure_fault" and request.context["fault"]["fault_key"] == "F08-BT-02":
                raise LLMError("refused (category None)")
            return super().call(request)

    doc = generate_category(make_inputs(), Flaky(), DATASET, workers=1, log=lambda _: None)
    assert doc["faults"]["F08-BT-02"]["error"] == "refused (category None)"
    assert "confirmation_test" in doc["faults"]["F08-BT-01"]


# ---------------------------------------------------------------- merge validation


def test_merge_validation_keeps_every_question_and_option_once():
    results = {
        "F01": {
            "follow_up_questions": [
                {
                    "text": "Hard pedal?",
                    "source": "symptoms",
                    "options": [
                        {"label": "Yes", "effect": "supports", "strength": "strong", "safety_trigger": False},
                        {"label": "No", "effect": "rules_out", "strength": "weak", "safety_trigger": False},
                        {"label": "Don't know", "effect": "neutral", "strength": "none", "safety_trigger": False},
                    ],
                }
            ]
        },
        "F02": {
            "follow_up_questions": [
                {
                    "text": "Is the pedal hard?",
                    "source": "stages_text",
                    "options": [
                        {"label": "Yes", "effect": "supports", "strength": "moderate", "safety_trigger": False},
                        {"label": "No", "effect": "rules_out", "strength": "moderate", "safety_trigger": False},
                    ],
                }
            ]
        },
        "F03": {
            "follow_up_questions": [
                {
                    "text": "Burning smell?",
                    "source": "symptoms",
                    "options": [
                        {"label": "Yes", "effect": "supports", "strength": "strong", "safety_trigger": True},
                        {"label": "No", "effect": "neutral", "strength": "none", "safety_trigger": False},
                    ],
                }
            ]
        },
    }
    raw = raw_questions(results)
    assert [o["label"] for o in raw[0]["options"]] == ["Yes", "No"]  # "Don't know" removed

    class BadMerge(FakeProvider):
        def call(self, request):  # duplicates, an unknown ref, and F03 left out entirely
            return {
                "groups": [
                    {
                        "canonical_text": "Does the pedal feel hard?",
                        "question_ids": ["F01#q1", "F02#q1", "F01#q1"],
                        "options": [
                            {"label": "Yes", "option_refs": ["F01#q1#o1", "F02#q1#o1", "F03#q1#o1"]},
                            {"label": "Not sure", "option_refs": ["F02#q1#o2"]},
                        ],
                    },
                ]
            }

    groups = merge_groups(raw, make_inputs(), BadMerge(), log=lambda _: None)
    assert sorted(i for g in groups for i in g["question_ids"]) == ["F01#q1", "F02#q1", "F03#q1"]
    pedal = next(g for g in groups if "F01#q1" in g["question_ids"])
    refs = sorted(r for o in pedal["options"] for r in o["option_refs"])
    assert refs == ["F01#q1#o1", "F01#q1#o2", "F02#q1#o1", "F02#q1#o2"]  # F03 ref rejected, unmapped kept
    assert {o["label"] for o in pedal["options"]} == {"Yes", "No"}  # model's "Not sure" option dropped


# ---------------------------------------------------------------- Anthropic request shape (stubbed client)


class StubMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.responses.pop(0)


def response(content, stop="end_turn"):
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=200,
        cache_read_input_tokens=500,
        cache_creation_input_tokens=0,
        iterations=None,
    )
    return SimpleNamespace(content=content, stop_reason=stop, stop_details=None, usage=usage, model="claude-opus-5-5")


def provider_with(responses) -> tuple[AnthropicProvider, StubMessages]:
    p = AnthropicProvider(model="claude-opus-5-5", effort="high", api_key="test-key")
    stub = StubMessages(responses)
    p.client = SimpleNamespace(beta=SimpleNamespace(messages=stub))
    return p, stub


REQ = ToolRequest(
    "structure_fault",
    "desc",
    {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    "static",
    "category",
    "fault text",
    {},
)


def test_anthropic_request_shape():
    tool = SimpleNamespace(type="tool_use", name="structure_fault", input={"ok": True})
    p, stub = provider_with([response([tool])])
    assert p.call(REQ) == {"ok": True}
    kw = stub.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["output_config"] == {"effort": "high"}
    assert kw["tools"][0]["strict"] is True and kw["tool_choice"] == {"type": "auto"}
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert kw["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in kw and "thinking" not in kw
    assert p.usage.calls == 1 and p.usage.cache_read_input_tokens == 500


def test_anthropic_retries_once_when_no_tool_call():
    text = SimpleNamespace(type="text", text="Here you go")
    tool = SimpleNamespace(type="tool_use", name="structure_fault", input={"ok": 1})
    p, stub = provider_with([response([text]), response([tool])])
    assert p.call(REQ) == {"ok": 1}
    assert len(stub.calls) == 2 and stub.calls[1]["messages"][-1]["content"].startswith("Please answer")


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_anthropic_refusal_and_truncation_raise(stop):
    p, _ = provider_with([response([], stop=stop)])
    with pytest.raises(LLMError):
        p.call(REQ)


def test_cost_estimate_uses_model_prices():
    u = Usage(calls=1, input_tokens=1_000_000, output_tokens=100_000, cache_read_input_tokens=1_000_000)
    assert u.cost_usd("claude-opus-5-5") == 4.0 + 2.0 + 0.2
    assert u.cost_usd("unknown-model") is None


# ---------------------------------------------------------------- review files


def test_drafts_never_overwrite_reviewed_work(tmp_path: Path):
    doc = generate_category(make_inputs(), FakeProvider(), DATASET, workers=1, log=lambda _: None)
    first = review.write_draft(doc, tmp_path)
    assert first.name == "battery.yaml" and first.read_text().startswith("# Draft questions")
    assert review.write_draft(doc, tmp_path).name == "battery.yaml"  # only drafts: safe to replace
    reviewed = review.read(first)
    reviewed["questions"][0]["status"] = "approved"
    first.write_text(review.dump(reviewed))
    assert review.write_draft(doc, tmp_path).name == "battery.new.yaml"
    assert review.status_counts(review.read(first))["approved"] == 1


def test_diff_against_last_load(tmp_path: Path):
    doc = generate_category(make_inputs(), FakeProvider(), DATASET, workers=1, log=lambda _: None)
    doc["questions"][0]["status"] = "approved"
    path = review.path_for("battery", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(review.dump(doc))
    assert "never loaded" in review.diff("battery", tmp_path)
    review.save_snapshot(doc, tmp_path)
    assert review.diff("battery", tmp_path).endswith("no changes")
    doc["questions"][0]["text"] = "What is wrong with the car?"
    doc["questions"][1]["status"] = "approved"
    path.write_text(review.dump(doc))
    out = review.diff("battery", tmp_path)
    assert "added 1, removed 0, changed 1" in out and "+ question battery-q01" in out
    assert "-text: What problem are you facing?" in out and "+text: What is wrong with the car?" in out


def test_run_log(tmp_path: Path):
    review.log_run({"category": "battery", "usage": {"input_tokens": 1}}, tmp_path)
    review.log_run({"category": "ac", "usage": {"input_tokens": 2}}, tmp_path)
    assert len((tmp_path / "runs.jsonl").read_text().splitlines()) == 2


# ---------------------------------------------------------------- loading (test database)


@pytest.fixture
def battery_db(db_session, tmp_path):
    """Import a small file-8 fixture (with a 'Choices:' line) into the test database."""
    rows = [
        fault(
            f"BT-0{i}",
            "BATTERY ISSUE",
            f"Battery fault {i}",
            question_stages='STAGE 2 - MAIN PROBLEM\n"What problem are you facing?"\n'
            "Choices: Car not starting | Self slow | Other",
        )
        for i in (1, 2, 3)
    ]
    path = make_workbook(tmp_path / "battery.xlsx", 4, rows)
    cfg = load_config()
    cfg.files = {8: dataclasses.replace(cfg.files[8], path=path)}
    cfg.review_dir, cfg.media_dir = tmp_path / "review", tmp_path / "media"
    run_import(db_session, cfg, [cfg.files[8]], all_files=True, embedder=FakeEmbedder(), log=lambda _: None)
    return db_session


@pytest.fixture
def battery_doc(battery_db):
    version = target_version(battery_db)
    inputs = category_inputs(battery_db, version, "battery")
    assert inputs["file_choices"] == ["Car not starting", "Self slow", "Other"] and inputs["draft_safety"]
    return generate_category(
        inputs, FakeProvider(), {"id": version.id, "checksum": version.checksum}, workers=1, log=lambda _: None
    )


def approve(doc, *ids, reviewer="Mechanic A"):
    doc["reviewed_by"] = reviewer
    for e in review.entries(doc).values():
        if e.get("id") in ids:
            e["status"] = "approved"
    return doc


def test_category_inputs_exclude_internal_items(battery_db):
    inputs = category_inputs(battery_db, target_version(battery_db), "battery")
    f = inputs["faults"][0]
    assert f["symptoms"] == ["Clicking sound", "Dim lights"]
    assert "mechanic_task" not in f and "Load test" not in str(f)


def test_load_only_approved_entries(battery_db, battery_doc):
    doc = approve(battery_doc, "battery-main", "battery-q01")
    doc["faults"]["F08-BT-01"]["status"] = "approved"
    report = load_document(battery_db, doc)
    assert report.questions == 2
    questions = battery_db.scalars(select(Question).order_by(Question.stage)).all()
    assert [q.stage for q in questions] == [2, 3] and all(q.status == "approved" for q in questions)
    assert questions[0].reviewed_by == "Mechanic A" and questions[0].created_by == "llm:fake-model"
    main_opts = [o.label_en for o in questions[0].options]
    assert main_opts == ["Car not starting", "Self slow", "Other", "Not sure"]
    assert sum(o.is_not_sure for o in questions[0].options) == 1
    f1 = battery_db.scalar(select(Fault).where(Fault.fault_key == "F08-BT-01"))
    assert f1.extra["structured"]["confirmation_test"].startswith("Mechanic confirms")
    weights = {float(e.weight) for e in battery_db.scalars(select(OptionEffect))}
    assert weights <= {1.0, 2.0, 3.0} and weights


def test_unapproving_and_reloading_removes_entries(battery_db, battery_doc):
    doc = approve(battery_doc, "battery-main", "battery-q01")
    load_document(battery_db, doc)
    doc["questions"][1]["status"] = "draft"
    load_document(battery_db, doc)
    assert [q.text_en for q in battery_db.scalars(select(Question))] == [doc["questions"][0]["text"]]


def test_load_requires_reviewer_and_valid_not_sure(battery_db, battery_doc):
    doc = approve(battery_doc, "battery-q01", reviewer="")
    with pytest.raises(ReviewFileError, match="reviewed_by"):
        load_document(battery_db, doc)
    doc["reviewed_by"] = "Mechanic A"
    doc["questions"][1]["options"] = [o for o in doc["questions"][1]["options"] if not o.get("not_sure")]
    with pytest.raises(ReviewFileError, match="Not sure"):
        load_document(battery_db, doc)


def test_approved_drafted_safety_rule_is_signed_off_with_triggers(battery_db, battery_doc):
    smoke = next(q for q in battery_doc["questions"] if "smoke" in q["text"].lower())
    doc = approve(battery_doc, smoke["id"], "battery-s-F08-BT-01")
    doc["faults"]["F08-BT-01"]["status"] = "approved"
    report = load_document(battery_db, doc)
    assert report.safety_rules == 1
    rule = battery_db.scalar(select(SafetyRule).where(SafetyRule.source == "drafted_from_columns"))
    assert rule.status == "approved" and rule.signed_off_by == "Mechanic A" and rule.signed_off_at is not None
    yes = battery_db.scalar(select(QuestionOption).where(QuestionOption.label_en == "Yes"))
    assert rule.triggers["option_ids"] == [yes.id]
    assert rule.triggers["phrases"] == ["smoke", "burning smell"]
    # Draft rules are not loaded.
    assert (
        battery_db.scalar(
            select(SafetyRule).where(SafetyRule.source == "drafted_from_columns", SafetyRule.status != "approved")
        )
        is None
    )
