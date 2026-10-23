"""Load approved review entries into the live tables. Draft and rejected entries are ignored.

The loader owns the category's questions: each load replaces them with the currently approved set,
so un-approving an entry and re-loading removes it. Effects are resolved by fault key in the target
dataset version; re-run the loader after re-importing the datasets.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.knowledge.models import Fault, OptionEffect, Question, QuestionOption, SafetyRule
from app.knowledge.questions.inputs import target_version

WEIGHTS = {"strong": 3, "moderate": 2, "weak": 1}


class ReviewFileError(Exception):
    pass


@dataclass
class LoadReport:
    category: str
    questions: int = 0
    options: int = 0
    effects: int = 0
    faults_updated: int = 0
    safety_rules: int = 0
    triggers_attached: int = 0
    skipped_effects: list[str] = field(default_factory=list)


def _check(doc: dict) -> None:
    approved = [q for q in doc.get("questions", []) if q.get("status") == "approved"]
    approved += [v for v in (doc.get("faults") or {}).values() if v.get("status") == "approved"]
    approved += [r for r in doc.get("safety_rules", []) if r.get("status") == "approved"]
    if approved and not (doc.get("reviewed_by") or "").strip():
        raise ReviewFileError("set reviewed_by at the top of the file before loading approved entries")
    for q in doc.get("questions", []):
        if q.get("status") != "approved":
            continue
        not_sure = [o for o in q["options"] if o.get("not_sure")]
        if len(not_sure) != 1 or not_sure[0].get("effects"):
            raise ReviewFileError(f"{q['id']}: needs exactly one 'Not sure' option (not_sure: true) with no effects")
        if len(q["options"]) < 3:
            raise ReviewFileError(f"{q['id']}: needs at least two answers plus 'Not sure'")
        labels = [o["label"].strip().lower() for o in q["options"]]
        if len(labels) != len(set(labels)):
            raise ReviewFileError(f"{q['id']}: duplicate option labels")
        for o in q["options"]:
            for e in o.get("effects", []):
                if e.get("effect") not in ("supports", "rules_out") or e.get("strength") not in WEIGHTS:
                    raise ReviewFileError(
                        f"{q['id']} / {o['label']}: effect must be supports|rules_out and strength strong|moderate|weak"
                    )


def load_document(session: Session, doc: dict) -> LoadReport:
    _check(doc)
    code = doc["category"]
    report = LoadReport(code)
    reviewer = doc["reviewed_by"].strip() if doc.get("reviewed_by") else ""
    now = datetime.now(UTC)
    version = target_version(session)
    faults = {
        f.fault_key: f
        for f in session.scalars(
            select(Fault).where(Fault.dataset_version_id == version.id, Fault.category_code == code)
        )
    }
    model = (doc.get("generated") or {}).get("model", "unknown")

    # Replace the category's questions with the approved set (options and effects cascade).
    session.execute(delete(Question).where(Question.category_code == code))
    session.flush()

    option_ids: dict[tuple[str, str], int] = {}
    for q in doc.get("questions", []):
        if q.get("status") != "approved":
            continue
        question = Question(
            category_code=code,
            stage=q["stage"],
            text_en=q["text"].strip(),
            status="approved",
            source_fault_ids=[faults[k].id for k in q.get("source_faults", []) if k in faults],
            created_by=f"llm:{model}",
            reviewed_by=q.get("approved_by") or reviewer,
            reviewed_at=now,
            version=(doc.get("generated") or {}).get("prompt_version", 1),
        )
        for pos, o in enumerate(q["options"]):
            option = QuestionOption(position=pos, label_en=o["label"].strip(), is_not_sure=bool(o.get("not_sure")))
            question.options.append(option)
        session.add(question)
        session.flush()
        report.questions += 1
        for o, option in zip(q["options"], question.options, strict=True):
            report.options += 1
            option_ids[(q["id"], o["label"].strip())] = option.id
            for e in o.get("effects", []):
                fault = faults.get(e["fault"])
                if fault is None:
                    report.skipped_effects.append(
                        f"{q['id']} / {o['label']}: fault {e['fault']} not in dataset version {version.id}"
                    )
                    continue
                session.add(
                    OptionEffect(
                        option_id=option.id, fault_id=fault.id, effect=e["effect"], weight=WEIGHTS[e["strength"]]
                    )
                )
                report.effects += 1
    session.flush()

    # Approved fault entries: structured extras on the fault row.
    triggers_by_fault: dict[str, dict] = {}
    for key, entry in (doc.get("faults") or {}).items():
        if entry.get("status") != "approved" or key not in faults:
            continue
        fault = faults[key]
        fault.extra = {
            **(fault.extra or {}),
            "structured": {
                "stage2_choices": entry.get("stage2_choices", []),
                "confirmation_test": entry.get("confirmation_test", ""),
                "danger_phrases": entry.get("danger_phrases", []),
                "approved_by": entry.get("approved_by") or reviewer,
            },
        }
        report.faults_updated += 1
        opts = [
            option_ids[(t["question"], t["option"])]
            for t in entry.get("safety_trigger_options", [])
            if (t["question"], t["option"]) in option_ids
        ]
        triggers_by_fault[key] = {"option_ids": opts, "phrases": entry.get("danger_phrases", [])}

    # Drafted safety rules: replace the category's drafted rules with the approved ones (signed off).
    fault_ids = [f.id for f in faults.values()]
    session.execute(
        delete(SafetyRule).where(SafetyRule.source == "drafted_from_columns", SafetyRule.fault_id.in_(fault_ids))
    )
    for r in doc.get("safety_rules", []):
        if r.get("status") != "approved" or r["fault"] not in faults:
            continue
        session.add(
            SafetyRule(
                dataset_version_id=version.id,
                scope="fault",
                fault_id=faults[r["fault"]].id,
                kind="general",
                risk_level=r["risk_level"],
                stop_driving_trigger=r["stop_driving_trigger"],
                roadside_action=r["roadside_action"],
                towing_recommendation=r["towing_recommendation"],
                triggers=triggers_by_fault.get(r["fault"], {}),
                status="approved",
                signed_off_by=r.get("approved_by") or reviewer,
                signed_off_at=now,
                source="drafted_from_columns",
                source_ref=f"data/review/questions/{code}.yaml {r['id']}",
            )
        )
        report.safety_rules += 1
    session.flush()

    # Sheet rules (pending sign-off) get the approved triggers of their fault; status is untouched.
    for key, triggers in triggers_by_fault.items():
        for rule in session.scalars(
            select(SafetyRule).where(SafetyRule.fault_id == faults[key].id, SafetyRule.source == "sheet")
        ):
            rule.triggers = triggers
            report.triggers_attached += 1
    session.flush()
    return report
