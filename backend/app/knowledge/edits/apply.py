"""Re-apply editor edits to a version: the published edits (the live knowledge), then the version's own draft
edits. Runs as a pipeline step after the reviewed files, so edits survive every Excel import."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.knowledge.edits.handlers import HANDLERS, Invalid, Orphan
from app.knowledge.edits.taxonomy import published_taxonomy
from app.knowledge.models import DatasetVersion, EditStatus, KnowledgeEdit


@dataclass
class ApplyReport:
    applied: int = 0
    conflicts: list[dict] = field(default_factory=list)  # the import changed an edited field too (the edit is kept)
    orphans: list[dict] = field(default_factory=list)  # the edited item is not in this version (not applied)

    def as_dict(self) -> dict:
        return {"applied": self.applied, "conflicts": self.conflicts, "orphans": self.orphans}


def edits_for(session: Session, version: DatasetVersion) -> list[KnowledgeEdit]:
    """Published edits (oldest first), then this version's draft edits (oldest first)."""
    published = session.scalars(
        select(KnowledgeEdit)
        .where(KnowledgeEdit.status == EditStatus.published)
        .order_by(KnowledgeEdit.published_at, KnowledgeEdit.id)
    ).all()
    own = session.scalars(
        select(KnowledgeEdit)
        .where(KnowledgeEdit.dataset_version_id == version.id, KnowledgeEdit.status == EditStatus.draft)
        .order_by(KnowledgeEdit.id)
    ).all()
    return [*published, *own]


def changed_fields(base: dict | None, data: dict | None) -> list[str]:
    if base is None or data is None:
        return sorted((data or base or {}).keys())
    return sorted(k for k in data if data.get(k) != base.get(k))


# Set by the loaders on every load (the question loader stamps reviewed_at with the load time): never a conflict.
VOLATILE = {"reviewed_at", "signed_off_at"}


def conflict(edit: KnowledgeEdit, now: dict | None) -> list[str]:
    """Fields the import changed since the edit was made (and the edit sets to something else)."""
    if edit.base is None:
        return ["item"] if now is not None and now != edit.data else []
    if now is None:
        return []
    return [
        k
        for k in changed_fields(edit.base, edit.data)
        if k not in VOLATILE and now.get(k) != edit.base.get(k) and now.get(k) != (edit.data or {}).get(k)
    ]


def apply_all(session: Session, version: DatasetVersion, taxonomy_base: dict, stage: str = "knowledge") -> ApplyReport:
    """Stage "knowledge" (before parts build): make the version's taxonomy taxonomy.yaml + published + its own edits,
    and apply the other knowledge edits to its rows. Stage "parts" (after parts build): the Parts & Prices edits.
    Changes to shared rows (photo labels, existing parts) are written at publish (apply_global)."""
    report = ApplyReport()
    if stage == "knowledge":
        version.taxonomy = published_taxonomy(session, taxonomy_base)
    for e in edits_for(session, version):
        h = HANDLERS.get(e.entity)
        if h is None or h.stage != stage:
            continue
        if h.global_table:
            h.write(session, version, e.key, e.data)  # a new part is created; existing shared rows wait for publish
            report.applied += 1
            continue
        if e.status == EditStatus.published and h.taxonomy:
            continue  # already in published_taxonomy()
        try:
            now = h.snapshot(session, version, e.key)
        except Invalid:
            now = None
        if e.base is not None and now is None and e.data is not None:
            report.orphans.append(_entry(e, "the item is not in this version (removed from the file?)"))
            continue
        if fields := conflict(e, now):
            report.conflicts.append(_entry(e, f"the import changed {', '.join(fields)} too; the edit is kept"))
        try:
            h.write(session, version, e.key, e.data)
            report.applied += 1
            if dropped := getattr(h, "dropped", None):
                report.conflicts.append(_entry(e, f"answer effects on faults no longer here were dropped: {dropped}"))
            if untriggered := getattr(h, "untriggered", None):
                report.conflicts.append(_entry(e, f"removed answers were safety triggers: {'; '.join(untriggered)}"))
        except Orphan:
            report.orphans.append(_entry(e, "the item is not in this version"))
        except Invalid as err:
            report.orphans.append(_entry(e, str(err)))
    session.flush()
    return report


def apply_global(session: Session, version: DatasetVersion) -> int:
    """At publish: write photo-label sign-offs (published ones and this version's) to the live list."""
    n = 0
    for e in session.scalars(
        select(KnowledgeEdit)
        .where(
            KnowledgeEdit.entity.in_([h.entity for h in HANDLERS.values() if h.global_table]),
            or_(
                KnowledgeEdit.status == EditStatus.published,
                (KnowledgeEdit.dataset_version_id == version.id) & (KnowledgeEdit.status == EditStatus.draft),
            ),
        )
        .order_by(KnowledgeEdit.id)
    ):
        try:
            HANDLERS[e.entity].write_live(session, e.key, e.data)
            n += 1
        except Orphan:
            continue
    return n


def _entry(e: KnowledgeEdit, message: str) -> dict:
    h = HANDLERS[e.entity]
    return {"edit": e.id, "entity": e.entity, "key": e.key, "name": h.name(e.key, e.data, e.base), "message": message}
