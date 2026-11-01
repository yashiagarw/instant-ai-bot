"""Checks on a draft against the version the app serves: nothing lost, and what changed (the diff).

Nothing lost: every artefact is counted per slot (category, fault key, detail) in both versions. A slot whose count
went down is a loss. Rows that come from the uploaded file itself (items, costs, dataset phrases, pictures) may change
only in the categories the upload changes; everything the reviewed files add (questions, effects, merges,
requirements, drafted phrases, parts links, trigger phrases) and every safety rule must survive for every fault that is
still there. Faults removed on purpose by the upload are not losses (the diff lists them).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import ReviewStatus
from app.knowledge.embeddings import sources as embedding_sources
from app.knowledge.models import (
    LIVE_SAFETY_STATUSES,
    CustomerPhrase,
    DatasetVersion,
    Embedding,
    Fault,
    FaultCost,
    FaultImage,
    FaultItem,
    FaultLink,
    FaultPrior,
    InspectionChecklistItem,
    LinkRelation,
    LinkSource,
    OptionEffect,
    PhraseSource,
    Question,
    QuestionOption,
    SafetyRule,
)
from app.parts.models import FaultPart
from app.vision.models import ImageLabel

GLOBAL = "*"  # slot category of rows that belong to no category

# artefact -> (label, comes from the uploaded file?). Safety rules are checked for every remaining fault even though
# sheet rules come from the file: a safety rule must never disappear without anyone noticing.
ARTEFACTS: dict[str, tuple[str, bool]] = {
    "questions": ("approved questions", False),
    "effects": ("question answer effects", False),
    "safety": ("safety rules", False),
    "triggers": ("safety trigger phrases", False),
    "drafted_phrases": ("reviewed customer phrases", False),
    "merges": ("duplicate merges", False),
    "requirements": ("fault requirements", False),
    "fault_parts": ("approved parts links", False),
    "priors": ("fault priors", False),
    "global_safety": ("emergency (global) safety rules", False),
    "items": ("fault lines (symptoms, causes, steps ...)", True),
    "dataset_phrases": ("customer phrases from the sheet", True),
    "costs": ("cost rows", True),
    "images": ("fault pictures", True),
    "checklist": ("inspection checklist items", True),
}


def _faults(session: Session, version_id: int) -> dict[int, tuple[str, str]]:
    return {
        fid: (key, cat)
        for fid, key, cat in session.execute(
            select(Fault.id, Fault.fault_key, Fault.category_code).where(Fault.dataset_version_id == version_id)
        )
    }


def artefacts(session: Session, version: DatasetVersion) -> dict[str, Counter]:
    """artefact -> Counter of slots (category, fault key or "", detail...)."""
    faults = _faults(session, version.id)
    ids = list(faults)
    out: dict[str, Counter] = {name: Counter() for name in ARTEFACTS}

    def slot(fid: int, *detail) -> tuple:
        key, cat = faults[fid]
        return (cat, key, *detail)

    for cat, stage, text_ in session.execute(
        select(Question.category_code, Question.stage, Question.text_en).where(
            Question.dataset_version_id == version.id, Question.status == ReviewStatus.approved
        )
    ):
        out["questions"][(cat, "", stage, text_)] += 1
    for fid, effect in session.execute(
        select(OptionEffect.fault_id, OptionEffect.effect)
        .join(QuestionOption, QuestionOption.id == OptionEffect.option_id)
        .join(Question, Question.id == QuestionOption.question_id)
        .where(Question.dataset_version_id == version.id)
    ):
        if fid in faults:
            out["effects"][slot(fid, str(effect))] += 1
    for fid, scope, source, kind, ref, triggers in session.execute(
        select(
            SafetyRule.fault_id,
            SafetyRule.scope,
            SafetyRule.source,
            SafetyRule.kind,
            SafetyRule.source_ref,
            SafetyRule.triggers,
        ).where(SafetyRule.dataset_version_id == version.id, SafetyRule.status.in_(list(LIVE_SAFETY_STATUSES)))
    ):
        has_triggers = bool((triggers or {}).get("phrases") or (triggers or {}).get("option_ids"))
        if fid is not None and fid in faults:
            out["safety"][slot(fid, str(scope), str(source), str(kind))] += 1
            if has_triggers:
                out["triggers"][slot(fid, str(source))] += 1
        elif str(scope) == "global":
            out["global_safety"][(GLOBAL, "", str(kind), ref)] += 1
            if has_triggers:
                out["triggers"][(GLOBAL, "", ref)] += 1
        else:
            out["safety"][(GLOBAL, "", str(scope), str(source), str(kind))] += 1
    for fid, source in session.execute(
        select(CustomerPhrase.fault_id, CustomerPhrase.source).where(
            CustomerPhrase.fault_id.in_(ids), CustomerPhrase.status == ReviewStatus.approved
        )
    ):
        out["drafted_phrases" if source == PhraseSource.drafted else "dataset_phrases"][slot(fid)] += 1
    for a, b in session.execute(
        select(FaultLink.from_fault_id, FaultLink.to_fault_id).where(
            FaultLink.from_fault_id.in_(ids),
            FaultLink.relation == LinkRelation.merged_into,
            FaultLink.source == LinkSource.manual,
        )
    ):
        if b in faults:
            out["merges"][slot(a, faults[b][0])] += 1
    for fid, requires in session.execute(select(Fault.id, Fault.requires).where(Fault.id.in_(ids))):
        if requires:
            out["requirements"][slot(fid)] += 1
    for fid, n in session.execute(
        select(FaultPart.fault_id, func.count())
        .where(FaultPart.fault_id.in_(ids), FaultPart.status == ReviewStatus.approved)
        .group_by(FaultPart.fault_id)
    ):
        out["fault_parts"][slot(fid)] += n
    for (fid,) in session.execute(select(FaultPrior.fault_id).where(FaultPrior.fault_id.in_(ids))):
        out["priors"][slot(fid)] += 1
    for fid, type_, n in session.execute(
        select(FaultItem.fault_id, FaultItem.type, func.count())
        .where(FaultItem.fault_id.in_(ids))
        .group_by(FaultItem.fault_id, FaultItem.type)
    ):
        out["items"][slot(fid, str(type_))] += n
    for fid, n in session.execute(
        select(FaultCost.fault_id, func.count()).where(FaultCost.fault_id.in_(ids)).group_by(FaultCost.fault_id)
    ):
        out["costs"][slot(fid)] += n
    for fid, n in session.execute(
        select(FaultImage.fault_id, func.count()).where(FaultImage.fault_id.in_(ids)).group_by(FaultImage.fault_id)
    ):
        out["images"][slot(fid)] += n
    for file_no, n in session.execute(
        select(InspectionChecklistItem.source_file_no, func.count())
        .where(InspectionChecklistItem.dataset_version_id == version.id)
        .group_by(InspectionChecklistItem.source_file_no)
    ):
        out["checklist"][(GLOBAL, "", f"file {file_no}")] += n
    return out


@dataclass
class Loss:
    area: str
    category: str
    fault_key: str
    detail: str
    before: int
    after: int

    def as_dict(self) -> dict:
        return {
            "area": self.area,
            "category": self.category,
            "fault_key": self.fault_key,
            "detail": self.detail,
            "before": self.before,
            "after": self.after,
        }


def losses(
    old: dict[str, Counter],
    new: dict[str, Counter],
    changed_categories: set[str],
    changed_files: set[int] = frozenset(),
    common_keys: set[str] | None = None,
) -> list[Loss]:
    """Slots whose count went down. File rows may change only in changed categories (and global file rows only for
    changed files); for faults the upload removed nothing is a loss."""
    out = []
    for name, (label, from_file) in ARTEFACTS.items():
        for slot_, before in old[name].items():
            after = new[name].get(slot_, 0)
            if after >= before:
                continue
            cat, key, *detail = slot_
            if key and common_keys is not None and key not in common_keys:
                continue  # the fault itself was removed by the upload (listed in the diff)
            if from_file and cat in changed_categories:
                continue
            if from_file and cat == GLOBAL and any(d == f"file {n}" for n in changed_files for d in detail):
                continue
            out.append(Loss(label, cat, key, " ".join(str(d) for d in detail), before, after))
    return out


def photo_label_losses(session: Session, resolved: list) -> list[Loss]:
    """Photo labels that link to symptom lines now but would link to none in the new version."""
    live = {lb.code for lb in session.scalars(select(ImageLabel)) if lb.symptom_ids}
    now = {r.code for r in resolved if r.symptom_ids}
    return [Loss("photo labels", GLOBAL, "", code, 1, 0) for code in sorted(live - now)]


def missing_embeddings(session: Session, version: DatasetVersion, model_name: str) -> int:
    """Searchable texts of the version without a vector of this model (0 after a complete sync)."""
    wanted = {(str(s.owner_type), s.owner_id) for s in embedding_sources(session, version.id)}
    have = {
        (str(t), i)
        for t, i in session.execute(
            select(Embedding.owner_type, Embedding.owner_id).where(
                Embedding.model_name == model_name,
                Embedding.fault_id.in_(select(Fault.id).where(Fault.dataset_version_id == version.id)),
            )
        )
    }
    return len(wanted - have)


# ---------------------------------------------------------------- diff

DIFF_FIELDS = (
    "name",
    "description",
    "likely_fault",
    "road_repairable_text",
    "repair_location",
    "towing_conditions_text",
    "repair_time_text",
    "question_stages_raw",
)
TEXT_LIMIT = 300


def _row(fault: Fault, items: dict, phrases: dict, costs: dict) -> dict:
    row = {f: getattr(fault, f) or "" for f in DIFF_FIELDS}
    for type_, lines in sorted(items.get(fault.id, {}).items()):
        row[f"items: {type_}"] = "\n".join(lines)
    row["customer phrases"] = "\n".join(sorted(phrases.get(fault.id, [])))
    for seg, text_ in sorted(costs.get(fault.id, {}).items()):
        row[f"cost: {seg}"] = text_
    return row


def _rows(session: Session, version_id: int, categories: set[str]) -> dict[str, tuple[Fault, dict]]:
    faults = session.scalars(
        select(Fault).where(Fault.dataset_version_id == version_id, Fault.category_code.in_(categories))
    ).all()
    ids = [f.id for f in faults]
    items: dict[int, dict[str, list[str]]] = {}
    for fid, type_, text_ in session.execute(
        select(FaultItem.fault_id, FaultItem.type, FaultItem.text)
        .where(FaultItem.fault_id.in_(ids))
        .order_by(FaultItem.fault_id, FaultItem.type, FaultItem.position)
    ):
        items.setdefault(fid, {}).setdefault(str(type_), []).append(text_)
    phrases: dict[int, list[str]] = {}
    for fid, text_ in session.execute(
        select(CustomerPhrase.fault_id, CustomerPhrase.text).where(
            CustomerPhrase.fault_id.in_(ids), CustomerPhrase.source == PhraseSource.dataset
        )
    ):
        phrases.setdefault(fid, []).append(text_)
    costs: dict[int, dict[str, str]] = {}
    for c in session.scalars(select(FaultCost).where(FaultCost.fault_id.in_(ids))):
        costs.setdefault(c.fault_id, {})[str(c.segment)] = (
            f"{c.display_mode}: {c.total_inr or ''} {c.total_min_inr or ''}-{c.total_max_inr or ''} "
            f"{c.total_text or ''}".strip()
        )
    return {f.fault_key: (f, _row(f, items, phrases, costs)) for f in faults}


def _short(value: str) -> str:
    return value if len(value) <= TEXT_LIMIT else value[: TEXT_LIMIT - 1] + "…"


def diff(session: Session, old: DatasetVersion | None, new: DatasetVersion, categories: set[str]) -> dict:
    """Added, changed and removed fault rows of these categories (new vs old), with the changed fields."""
    before = _rows(session, old.id, categories) if old else {}
    after = _rows(session, new.id, categories)
    added = [
        {"fault_key": k, "category": f.category_code, "name": f.name} for k, (f, _) in sorted(after.items())
        if k not in before
    ]  # fmt: skip
    removed = [
        {"fault_key": k, "category": f.category_code, "name": f.name} for k, (f, _) in sorted(before.items())
        if k not in after
    ]  # fmt: skip
    changed = []
    for key in sorted(set(before) & set(after)):
        (f_old, r_old), (f_new, r_new) = before[key], after[key]
        fields = [
            {"field": name, "before": _short(r_old.get(name, "")), "after": _short(r_new.get(name, ""))}
            for name in sorted(set(r_old) | set(r_new))
            if r_old.get(name, "") != r_new.get(name, "")
        ]
        if fields or f_old.category_code != f_new.category_code:
            changed.append({"fault_key": key, "category": f_new.category_code, "name": f_new.name, "fields": fields})
    return {
        "categories": sorted(categories),
        "added": added,
        "changed": changed,
        "removed": removed,
        "unchanged": len(set(before) & set(after)) - len(changed),
    }
