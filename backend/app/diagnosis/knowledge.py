"""Build the engine's Knowledge snapshot from the database (customer-facing fields only).

The engine never touches the database; this module is the only bridge. Internal fields (mechanic task,
mechanic repair steps, internal notes) are never read here.
"""

import dataclasses
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.enums import ReviewStatus
from app.knowledge.models import (
    INTERNAL_ITEM_TYPES,
    LIVE_SAFETY_STATUSES,
    Category,
    CustomerPhrase,
    Fault,
    FaultCost,
    FaultItem,
    FaultItemType,
    FaultLink,
    InspectionChecklistItem,
    LinkRelation,
    OptionEffect,
    OptionEffectKind,
    PartPriceSource,
    PartPriceSourceFault,
    PartVerification,
    ProblemGroup,
    Question,
    SafetyRule,
)
from app.knowledge.questions.inputs import target_version
from engine import types as et


def _vector(v) -> list[float] | None:
    return None if v is None else [float(x) for x in v]


def _known(cls, **kwargs):
    """Build an engine dataclass with only the fields it defines, so an older engine version (data/eval compare
    mode) can still load today's knowledge. New fields simply stay at their defaults there."""
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in kwargs.items() if k in names})


def load_knowledge(session: Session) -> et.Knowledge:
    version = target_version(session)

    categories = {
        c.code: et.Category(
            code=c.code,
            name=c.name,
            kind=str(c.kind),
            filters=list(c.vehicle_filters or []),
            wave=float(c.wave),
            source_files=tuple(sorted({s.file_no for s in c.sources})),
        )
        for c in session.scalars(select(Category).options(selectinload(Category.sources)))
    }
    groups = {
        g.code: et.Group(
            code=g.code,
            group_type=str(g.group_type),
            label=g.label_en,
            categories=[pc.category_code for pc in g.categories],
            mode=str(g.mode) if g.mode else None,
            variants=list(g.variants or []),
        )
        for g in session.scalars(select(ProblemGroup).options(selectinload(ProblemGroup.categories)))
    }

    rows = session.scalars(select(Fault).where(Fault.dataset_version_id == version.id).order_by(Fault.id)).all()
    faults = {
        f.id: et.Fault(
            id=f.id,
            key=f.fault_key,
            category=f.category_code,
            name=f.name,
            road_repairable=str(f.road_repairable),
            road_repairable_text=f.road_repairable_text,
            towing_text=f.towing_conditions_text,
            repair_time_text=f.repair_time_text,
            stage2_choices=list(f.stage2_choices or []),
        )
        for f in rows
    }
    ids = list(faults)

    texts: list[et.TextEntry] = []
    items = session.scalars(
        select(FaultItem).where(
            FaultItem.fault_id.in_(ids),
            FaultItem.type.in_([FaultItemType.symptom, FaultItemType.safety]),
            FaultItem.internal.is_(False),
        )
    )
    for it in items:
        assert it.type not in INTERNAL_ITEM_TYPES
        if it.type == FaultItemType.symptom:
            texts.append(et.TextEntry(it.fault_id, it.text, "symptom", _vector(it.embedding)))
        else:
            faults[it.fault_id].safety_tips.append(it.text)
    phrases = session.scalars(
        select(CustomerPhrase).where(
            CustomerPhrase.fault_id.in_(ids),
            CustomerPhrase.status == ReviewStatus.approved,
            CustomerPhrase.held_out.is_(False),  # held-out phrases are the evaluation set
        )
    )
    for p in phrases:
        texts.append(et.TextEntry(p.fault_id, p.text, "phrase", _vector(p.embedding)))
        if p.english_gloss:
            texts.append(et.TextEntry(p.fault_id, p.english_gloss, "phrase"))

    for c in session.scalars(select(FaultCost).where(FaultCost.fault_id.in_(ids))):
        faults[c.fault_id].costs[str(c.segment)] = _known(
            et.Cost,
            segment=str(c.segment),
            display=str(c.display_mode),
            total=c.total_inr,
            total_min=c.total_min_inr,
            total_max=c.total_max_inr,
            text=c.total_text,
            approx_label=c.approx_label,
            checked_on=c.checked_on.isoformat() if c.checked_on else None,
            is_approx=c.is_approx,
            needs_review=c.needs_review,
            labour=c.labour_inr,
            labour_text=c.labour_text,
        )

    fits = session.execute(
        select(PartPriceSourceFault.fault_id, PartPriceSource.vehicle_fit_text)
        .join(PartPriceSource, PartPriceSource.id == PartPriceSourceFault.part_price_source_id)
        .where(
            PartPriceSourceFault.fault_id.in_(ids),
            PartPriceSourceFault.status == ReviewStatus.approved,
            PartPriceSource.verification_status == PartVerification.checked,
        )
    )
    for fault_id, fit_text in fits:
        if fit_text:
            faults[fault_id].part_fit_texts.append(fit_text)

    questions: dict[int, et.Question] = {}
    q_rows = session.scalars(
        select(Question)
        .where(Question.status == ReviewStatus.approved, Question.category_code.in_(list(categories)))
        .options(selectinload(Question.options))
    ).all()
    option_ids = [o.id for q in q_rows for o in q.options]
    effects: dict[int, dict[int, float]] = {}
    for e in session.scalars(select(OptionEffect).where(OptionEffect.option_id.in_(option_ids))):
        if e.fault_id in faults:
            sign = 1.0 if e.effect == OptionEffectKind.supports else -1.0
            effects.setdefault(e.option_id, {})[e.fault_id] = sign * float(e.weight)
    for q in q_rows:
        questions[q.id] = et.Question(
            id=q.id,
            category=q.category_code,
            stage=q.stage,
            text=q.text_en,
            options=[et.Option(o.id, o.label_en, o.is_not_sure, effects.get(o.id, {})) for o in q.options],
        )

    rules = []
    for r in session.scalars(
        select(SafetyRule).where(
            SafetyRule.dataset_version_id == version.id, SafetyRule.status.in_(list(LIVE_SAFETY_STATUSES))
        )
    ):
        m = re.match(r"F(\d+)\b", r.source_ref or "")
        triggers = r.triggers or {}
        rules.append(
            et.SafetyRule(
                id=r.id,
                scope=str(r.scope),
                risk=str(r.risk_level),
                stop_trigger=r.stop_driving_trigger,
                roadside_action=r.roadside_action,
                towing=r.towing_recommendation,
                fault_id=r.fault_id,
                category=r.category_code,
                option_ids=set(triggers.get("option_ids", [])),
                phrases=list(triggers.get("phrases", [])),
                source_file=int(m.group(1)) if m else None,
            )
        )

    checklist = [
        et.ChecklistItem(i.system, i.method)
        for i in session.scalars(
            select(InspectionChecklistItem)
            .where(InspectionChecklistItem.dataset_version_id == version.id)
            .order_by(InspectionChecklistItem.position)
        )
    ]
    links = session.execute(
        select(FaultLink.from_fault_id, FaultLink.to_fault_id).where(
            FaultLink.relation == LinkRelation.merged_into, FaultLink.from_fault_id.in_(ids)
        )
    ).all()
    alias_of = fold_aliases(faults, texts, questions, rules, {a: c for a, c in links if c in faults})
    return et.Knowledge(version.id, categories, groups, faults, texts, questions, rules, checklist, alias_of)


def fold_aliases(faults, texts, questions, rules, alias_of: dict[int, int]) -> dict[int, int]:
    """Apply merged_into links. A same-category alias is folded into its canonical fault: its phrases,
    symptoms, safety lines, part fits, option effects (where the canonical has none) and safety rules move
    over and the alias leaves `faults`. A cross-category alias stays in its own category. Returns alias_of."""
    for alias, canonical in alias_of.items():
        a, c = faults[alias], faults[canonical]
        c.alias_keys.append(a.key)
        if a.category != c.category:
            continue
        for t in texts:
            if t.fault_id == alias:
                t.fault_id = canonical
        c.safety_tips += [x for x in a.safety_tips if x not in c.safety_tips]
        c.part_fit_texts += [x for x in a.part_fit_texts if x not in c.part_fit_texts]
        for q in questions.values():
            for o in q.options:
                if alias in o.effects:
                    weight = o.effects.pop(alias)
                    o.effects.setdefault(canonical, weight)
        for r in rules:
            if r.fault_id == alias:
                r.fault_id = canonical
        del faults[alias]
    return alias_of


def sentence_embedder():
    """The same model the importer used for the stored vectors, as a text -> vector callable."""
    from app.knowledge.importer.embed import SentenceTransformerEmbedder

    model = SentenceTransformerEmbedder()
    return lambda text: model.encode([text])[0]
