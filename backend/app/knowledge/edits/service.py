"""Save, revert and sign off editor edits; publish them with their version; summarise a draft's edits."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.admin import audit
from app.knowledge.edits.apply import changed_fields
from app.knowledge.edits.handlers import HANDLERS, Invalid, Orphan
from app.knowledge.models import DatasetOrigin, DatasetStatus, DatasetVersion, EditStatus, KnowledgeEdit

SIGNOFF_FIELDS = {
    "question": ("reviewed_by", "reviewed_at"),
    "phrase": ("reviewed_by", "reviewed_at"),
    "safety_rule": ("signed_off_by", "signed_off_at"),
    "image_label": ("reviewed_by", "reviewed_at"),
}


class Actor:
    def __init__(self, id, label: str, ip: str | None = None):
        self.id, self.label, self.ip = id, label, ip


def editable(version: DatasetVersion) -> None:
    if version.status not in (DatasetStatus.draft, DatasetStatus.validated) or version.origin in (
        DatasetOrigin.import_,
        DatasetOrigin.rollback,
    ):
        raise Invalid("Edits go into an open draft (an edit draft or an uploaded draft), never the live version.")


def save(
    session: Session,
    version: DatasetVersion,
    actor: Actor,
    entity: str,
    key: str,
    data: dict | None,
    reason: str = "",
    *,
    signoff: bool = False,
) -> KnowledgeEdit | None:
    """Validate, apply to the draft, keep as an override and audit. One pending edit per item and draft: a second
    save updates it (its `base` stays the state before the first). Saving the original state again removes it.
    Returns the edit (None when it was removed)."""
    editable(version)
    h = HANDLERS.get(entity)
    if h is None:
        raise Invalid(f"unknown item type {entity}")
    pending = session.scalar(
        select(KnowledgeEdit).where(
            KnowledgeEdit.dataset_version_id == version.id,
            KnowledgeEdit.entity == entity,
            KnowledgeEdit.key == key,
            KnowledgeEdit.status == EditStatus.draft,
        )
    )
    now = h.snapshot(session, version, key)
    base = pending.base if pending else now
    data = h.validate(data, exists=now is not None)
    if now is None and data is None:
        raise Orphan(key)
    h.check(session, version, key, data)
    try:
        with session.begin_nested():
            h.write(session, version, key, data)
    except Orphan as e:
        raise Invalid(f"{h.name(key, data, base)} is not in this draft") from e
    version.eval = {}  # the data changed: the evaluation must run again before publishing
    action = "knowledge.safety_edit" if h.safety else ("knowledge.signoff" if signoff else "knowledge.edit")
    fields = changed_fields(base, data)
    audit.record(
        session,
        actor_id=actor.id,
        actor_label=actor.label,
        action=action,
        entity_type=f"knowledge.{entity}",
        entity_id=key,
        before=None if base is None else {k: base.get(k) for k in fields} | {"version": version.id},
        after=None if data is None else {k: data.get(k) for k in fields} | ({"reason": reason} if reason else {}),
        ip=actor.ip,
    )
    if data == base:
        if pending is not None:
            session.delete(pending)
        session.flush()
        return None
    edit = pending or KnowledgeEdit(dataset_version_id=version.id, entity=entity, key=key, base=base)
    edit.data, edit.safety, edit.reason = data, h.safety, reason or edit.reason
    edit.signoff = signoff and (pending is None or pending.signoff)
    edit.created_by_id, edit.created_by, edit.updated_at = actor.id, actor.label, datetime.now(UTC)
    session.add(edit)
    session.flush()
    return edit


def sign_off(session: Session, version: DatasetVersion, actor: Actor, entity: str, key: str) -> KnowledgeEdit | None:
    """Mark an item as reviewed under the actor's name and today's date (for a safety rule: approved)."""
    if entity not in SIGNOFF_FIELDS:
        raise Invalid(f"{entity} has no sign-off")
    h = HANDLERS[entity]
    now = h.snapshot(session, version, key)
    if now is None:
        raise Invalid(f"{key} is not in this draft")
    who, when = SIGNOFF_FIELDS[entity]
    data = {**now, who: actor.label, when: datetime.now(UTC).isoformat(timespec="seconds")}
    if entity == "safety_rule":
        data["status"] = "approved"
    if entity == "image_label":
        data["reviewed"] = True
    return save(session, version, actor, entity, key, data, "sign-off", signoff=True)


def revert(session: Session, version: DatasetVersion, actor: Actor, edit: KnowledgeEdit) -> None:
    """Undo a pending edit: the item goes back to its state before the edit."""
    editable(version)
    if edit.status != EditStatus.draft or edit.dataset_version_id != version.id:
        raise Invalid("Only a pending edit of this draft can be reverted.")
    h = HANDLERS[edit.entity]
    try:
        with session.begin_nested():
            h.write(session, version, edit.key, edit.base)
    except (Orphan, Invalid) as e:
        raise Invalid(f"Cannot revert {h.name(edit.key, edit.data, edit.base)}: {e}. Rebuild the draft instead.") from e
    version.eval = {}
    audit.record(
        session,
        actor_id=actor.id,
        actor_label=actor.label,
        action="knowledge.safety_edit_revert" if edit.safety else "knowledge.edit_revert",
        entity_type=f"knowledge.{edit.entity}",
        entity_id=edit.key,
        before=edit.data,
        after=edit.base,
        ip=actor.ip,
    )
    session.delete(edit)
    session.flush()


def publish(session: Session, version: DatasetVersion) -> int:
    """The draft's edits become part of the live knowledge (called in the publish transaction)."""
    now = datetime.now(UTC)
    mine = session.scalars(
        select(KnowledgeEdit).where(
            KnowledgeEdit.dataset_version_id == version.id, KnowledgeEdit.status == EditStatus.draft
        )
    ).all()
    for e in mine:
        session.execute(
            update(KnowledgeEdit)
            .where(
                KnowledgeEdit.status == EditStatus.published,
                KnowledgeEdit.entity == e.entity,
                KnowledgeEdit.key == e.key,
            )
            .values(status=EditStatus.replaced)
        )
        e.status, e.published_at = EditStatus.published, now
    session.flush()
    return len(mine)


def draft_edits(session: Session, version: DatasetVersion) -> list[KnowledgeEdit]:
    return list(
        session.scalars(
            select(KnowledgeEdit)
            .where(KnowledgeEdit.dataset_version_id == version.id, KnowledgeEdit.status != EditStatus.replaced)
            .order_by(KnowledgeEdit.id)
        )
    )


def summary(session: Session, version: DatasetVersion) -> dict:
    """For the publish page: edits per table (added / changed / deleted / signed off) and every safety change by name
    with its old and new values."""
    counts: dict[str, Counter] = {}
    safety = []
    for e in draft_edits(session, version):
        h = HANDLERS[e.entity]
        op = "signed off" if e.signoff else "added" if e.base is None else "deleted" if e.data is None else "changed"
        counts.setdefault(h.label, Counter())[op] += 1
        if e.safety:
            fields = changed_fields(e.base, e.data)
            safety.append(
                {
                    "edit": e.id,
                    "name": h.name(e.key, e.data, e.base),
                    "key": e.key,
                    "by": e.created_by,
                    "changes": [
                        {"field": f, "before": (e.base or {}).get(f), "after": (e.data or {}).get(f)} for f in fields
                    ],
                }
            )
    return {"tables": {k: dict(v) for k, v in sorted(counts.items())}, "safety": safety}


def scope(session: Session, version: DatasetVersion) -> dict[str, set[str]]:
    """What the draft's edits touch: categories, fault keys and global safety rules (for the diff, the eval scope and
    the 'nothing lost' check, where these are intended changes, not losses). A safety loss is intended only where a
    safety rule itself was edited or its fault deleted (safety_fault_keys), never as a side effect of another edit."""
    cats: set[str] = set()
    keys: set[str] = set()
    rules: set[str] = set()
    safety_keys: set[str] = set()  # faults whose safety rules were edited (or that were deleted)
    for e in draft_edits(session, version):
        if e.status != EditStatus.draft:
            continue
        h = HANDLERS[e.entity]
        cats |= h.categories(session, version, e.key)
        if e.entity == "question":  # its answers' effects point at faults: changing them is intended
            keys |= {x["fault"] for d in (e.base, e.data) if d for o in d["options"] for x in o["effects"]}
        if e.entity == "fault" and (e.base or {}).get("category_code"):
            cats.add(e.base["category_code"])  # a deleted fault is no longer there to ask
        keys |= h.fault_keys(e.key)
        if e.entity == "safety_rule" and e.key.startswith("global/"):
            rules.add(e.key.removeprefix("global/"))
        elif e.entity == "safety_rule" or (e.entity == "fault" and e.data is None):
            safety_keys |= h.fault_keys(e.key)
    return {"categories": cats, "fault_keys": keys, "global_rules": rules, "safety_fault_keys": safety_keys}
