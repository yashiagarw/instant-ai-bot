"""Read the imported knowledge tables for one category (customer-facing fields only)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.models import Category, DatasetOrigin, DatasetVersion, DiagnosisRuleRaw, Fault, SafetyRule


def target_version(session: Session) -> DatasetVersion:
    """The dataset version the app serves: the published one, else the newest unpublished import (before the first
    publish). Drafts uploaded on the admin Datasets page are never served before they are published."""
    version = session.scalar(select(DatasetVersion).where(DatasetVersion.status == "published"))
    version = version or session.scalar(
        select(DatasetVersion)
        .where(DatasetVersion.status.in_(["validated", "draft"]), DatasetVersion.origin == DatasetOrigin.import_)
        .order_by(DatasetVersion.id.desc())
        .limit(1)
    )
    if version is None:
        raise SystemExit("No dataset version found. Run the importer first: python -m app.knowledge.importer --all")
    return version


def category_inputs(session: Session, version: DatasetVersion, code: str) -> dict:
    category = session.get(Category, code)
    if category is None:
        raise SystemExit(f"Unknown category '{code}'")
    faults = session.scalars(
        select(Fault)
        .where(Fault.dataset_version_id == version.id, Fault.category_code == code)
        .order_by(Fault.source_file_no, Fault.source_row)
    ).all()
    if not faults:
        raise SystemExit(f"Category '{code}' has no faults in dataset version {version.id}")
    ids = [f.id for f in faults]
    raw = {
        r.fault_id: r.columns
        for r in session.scalars(select(DiagnosisRuleRaw).where(DiagnosisRuleRaw.fault_id.in_(ids)))
    }
    sheet_rules = set(
        session.scalars(select(SafetyRule.fault_id).where(SafetyRule.fault_id.in_(ids), SafetyRule.source == "sheet"))
    )

    out = []
    for f in faults:
        items = {}
        for item in f.items:
            if not item.internal:  # mechanic-only text never goes to the model
                items.setdefault(item.type, []).append(item.text)
        out.append(
            {
                "fault_key": f.fault_key,
                "name": f.name,
                "description": f.description,
                "symptoms": items.get("symptom", []),
                "causes": items.get("cause", []),
                "likely_fault": f.likely_fault,
                "stages": f.question_stages_raw,
                "stage2_choices": list(f.stage2_choices or []),
                "diagnosis_rules": raw.get(f.id),
                "safety_precautions": f.source_cells.get("safety_precautions", ""),
                "towing_conditions": f.towing_conditions_text,
                "has_sheet_safety_rule": f.id in sheet_rules,
            }
        )
    # File choices: files 8-18 list the same "Choices:/Options:" line on every row of a category.
    file_choices: list[str] = []
    for f in out:
        for c in f["stage2_choices"]:
            if c not in file_choices:
                file_choices.append(c)
    return {
        "category": {"code": category.code, "name": category.name, "kind": category.kind},
        "faults": out,
        "file_choices": file_choices,
        "draft_safety": not any(f["has_sheet_safety_rule"] for f in out),
    }
