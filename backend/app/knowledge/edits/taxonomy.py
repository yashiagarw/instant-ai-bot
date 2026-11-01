"""The taxonomy per dataset version. taxonomy.yaml is the base; editor edits (categories, tiles, the emergency row,
vehicle filters) are applied on top and stored in dataset_versions.taxonomy. The live tables (categories,
problem_groups, problem_group_categories) are synced from the published version's taxonomy at publish, and from
taxonomy.yaml + published edits on every import, so an import never undoes a published taxonomy edit."""

from __future__ import annotations

import copy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.models import DatasetVersion, EditStatus, KnowledgeEdit

TAXONOMY_ENTITIES = ("category", "group", "vehicle_filter")


def published_taxonomy(session: Session, base: dict) -> dict:
    """taxonomy.yaml (`base`) with every published taxonomy edit applied."""
    from app.knowledge.edits.handlers import HANDLERS

    tax = copy.deepcopy(base)
    edits = session.scalars(
        select(KnowledgeEdit)
        .where(KnowledgeEdit.status == EditStatus.published, KnowledgeEdit.entity.in_(TAXONOMY_ENTITIES))
        .order_by(KnowledgeEdit.published_at, KnowledgeEdit.id)
    )
    for e in edits:
        try:
            HANDLERS[e.entity].write_taxonomy(tax, e.key, e.data)
        except KeyError:
            continue  # the item left taxonomy.yaml: reported as an orphan when a draft is built
    return tax


def version_taxonomy(session: Session, version: DatasetVersion, base: dict) -> dict:
    """The taxonomy a version serves (a copy): its own, else taxonomy.yaml + published edits."""
    return copy.deepcopy(version.taxonomy) if version.taxonomy else published_taxonomy(session, base)


def groups_of(tax: dict) -> list[tuple[dict, str, str]]:
    """(group, group_type, mode) in display order: tiles, emergency topics, inspection."""
    out = [(t, "tile", "diagnose") for t in tax.get("tiles", [])]
    out += [(t, "emergency", "fast_track") for t in (tax.get("emergency") or {}).get("topics", [])]
    if tax.get("inspection"):
        out.append((tax["inspection"], "inspection", "inspect"))
    return out


def category_filters(tax: dict, names: list[str]) -> list[dict]:
    filters = tax.get("vehicle_filters") or {}
    return [{"name": f, **filters[f]} for f in names if f in filters]
