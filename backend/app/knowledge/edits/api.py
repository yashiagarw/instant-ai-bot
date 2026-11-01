"""/api/admin/knowledge: the Knowledge editors and the generated-question queue. Reads come from a draft version;
every save is an edit in that draft (app.knowledge.edits.service), published through the dataset pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.permissions import Perm
from app.datasets.api import job_out, start_job
from app.datasets.pipeline import live_version
from app.db import get_session
from app.knowledge.edits import service
from app.knowledge.edits.apply import changed_fields
from app.knowledge.edits.handlers import (
    HANDLERS,
    ITEM_TYPES,
    Invalid,
    Orphan,
    next_fault_key,
    pending,
    phrase_key,
)
from app.knowledge.edits.taxonomy import groups_of, version_taxonomy
from app.knowledge.importer.config import load_config
from app.knowledge.models import (
    CustomerPhrase,
    DatasetOrigin,
    DatasetStatus,
    DatasetVersion,
    EditStatus,
    Fault,
    FaultItem,
    Image,
    JobKind,
    KnowledgeEdit,
    PhraseSource,
    Question,
    SafetyRule,
    SafetyStatus,
)
from app.llm.models import GeneratedQuestion, GeneratedStatus

router = APIRouter(prefix="/admin/knowledge", tags=["admin"], dependencies=[Depends(enforce)])
DbSession = Annotated[Session, Depends(get_session)]
SAFETY_WARNING = (
    "This changes a safety rule. Safety rules decide when customers are told to stop driving: the change is "
    "written to the audit log with the old and new values."
)


def _actor(staff) -> service.Actor:
    return service.Actor(staff.user.id, staff.label, staff.ip)


def _version(session: Session, version_id: int) -> DatasetVersion:
    v = session.get(DatasetVersion, version_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset version not found")
    return v


def _media_url(path: str) -> str:
    return "/media/" + path.removeprefix("data/media/")


def _pending_keys(session: Session, version: DatasetVersion) -> dict[str, int]:
    """'entity:key' -> edit id, for this draft's pending edits (the editors mark edited items)."""
    return {
        f"{e.entity}:{e.key}": e.id
        for e in session.scalars(
            select(KnowledgeEdit).where(
                KnowledgeEdit.dataset_version_id == version.id, KnowledgeEdit.status == EditStatus.draft
            )
        )
    }


# ---------------------------------------------------------------- drafts


class DraftOut(BaseModel):
    id: int
    origin: str
    status: str
    category_code: str | None
    created_by: str | None
    base_version_id: int | None
    stale: bool
    edits: int
    building: bool


@router.get("/drafts", response_model=list[DraftOut])
@requires(Perm.content_read)
def drafts(session: DbSession):
    """Open drafts the editors can write to (edit drafts and uploaded drafts), newest first."""
    live = live_version(session)
    out = []
    for v in session.scalars(
        select(DatasetVersion)
        .where(
            DatasetVersion.status.in_([DatasetStatus.draft, DatasetStatus.validated]),
            DatasetVersion.origin.in_([DatasetOrigin.edit, DatasetOrigin.upload]),
        )
        .order_by(DatasetVersion.id.desc())
    ):
        n = session.scalar(
            select(func.count()).where(
                KnowledgeEdit.dataset_version_id == v.id, KnowledgeEdit.status == EditStatus.draft
            )
        )
        out.append(
            DraftOut(
                id=v.id,
                origin=str(v.origin),
                status=str(v.status),
                category_code=v.category_code,
                created_by=v.created_by,
                base_version_id=v.base_version_id,
                stale=live is not None and live.status == DatasetStatus.published and v.base_version_id != live.id,
                edits=n or 0,
                building=not (v.validation or {}).get("checks") and not (v.validation or {}).get("error"),
            )
        )
    return out


@router.post("/drafts", status_code=status.HTTP_202_ACCEPTED, responses={409: {}, 503: {}})
@requires(Perm.knowledge_edit)
def start_draft(request: Request, staff: CurrentStaff, session: DbSession):
    """Start an edit draft: a copy of the live version (built in the background, about a minute and a half)."""
    live = live_version(session)
    if live is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Import the datasets once first")
    v = DatasetVersion(
        checksum="pending",
        status=DatasetStatus.draft,
        origin=DatasetOrigin.edit,
        base_version_id=live.id,
        created_by=staff.label,
    )
    session.add(v)
    session.flush()
    job = start_job(request, session, staff, JobKind.build, v, "dataset.edit_draft")
    return {"version_id": v.id, "job": job_out(job)}


# ---------------------------------------------------------------- reads


@router.get("/versions/{version_id}/taxonomy")
@requires(Perm.content_read)
def taxonomy(version_id: int, session: DbSession):
    """Tiles, emergency topics, the inspection booking, categories and vehicle filters as this version has them."""
    v = _version(session, version_id)
    tax = version_taxonomy(session, v, load_config().taxonomy)
    edited = _pending_keys(session, v)
    groups = []
    for g, _group_type, _mode in groups_of(tax):
        snap = HANDLERS["group"].read_taxonomy(tax, g["code"])
        groups.append({"code": g["code"], **snap, "edit": edited.get(f"group:{g['code']}")})
    cats = [
        {
            "code": c["code"],
            "sources": c.get("sources", []),
            **HANDLERS["category"].read_taxonomy(tax, c["code"]),
            "edit": edited.get(f"category:{c['code']}"),
        }
        for c in tax["categories"]
    ]
    filters = [
        {
            "name": name,
            **HANDLERS["vehicle_filter"].read_taxonomy(tax, name),
            "edit": edited.get(f"vehicle_filter:{name}"),
        }
        for name in sorted(tax.get("vehicle_filters") or {})
    ]
    return {"groups": groups, "categories": cats, "vehicle_filters": filters}


@router.get("/versions/{version_id}/faults")
@requires(Perm.content_read)
def faults(
    version_id: int,
    session: DbSession,
    category: Annotated[str | None, Query()] = None,
):
    """Faults of the version (optionally one category) with line counts and whether the draft edited them."""
    v = _version(session, version_id)
    q = select(Fault).where(Fault.dataset_version_id == v.id).order_by(Fault.category_code, Fault.fault_key)
    if category:
        q = q.where(Fault.category_code == category)
    rows = session.scalars(q).all()
    counts: dict[int, dict[str, int]] = {}
    for fid, type_, n in session.execute(
        select(FaultItem.fault_id, FaultItem.type, func.count())
        .where(FaultItem.fault_id.in_([f.id for f in rows]))
        .group_by(FaultItem.fault_id, FaultItem.type)
    ):
        counts.setdefault(fid, {})[str(type_)] = n
    edited = {k.split(":", 1)[1].split("/")[0].split("|")[0] for k in _pending_keys(session, v)}
    return [
        {
            "key": f.fault_key,
            "name": f.name,
            "category": f.category_code,
            "needs_review": f.needs_review,
            "safety_critical": f.safety_critical,
            "lines": counts.get(f.id, {}),
            "edited": f.fault_key in edited,
            "new": bool((f.extra or {}).get("created_in_editor")),
        }
        for f in rows
    ]


@router.get("/versions/{version_id}/faults/{fault_key}", responses={404: {}})
@requires(Perm.content_read)
def fault_detail(version_id: int, fault_key: str, session: DbSession):
    """Everything the fault editor shows: details, applicability, weight, every line type, phrases, pictures and
    safety rules (each with its edit key and whether this draft changed it)."""
    v = _version(session, version_id)
    f = session.scalar(select(Fault).where(Fault.dataset_version_id == v.id, Fault.fault_key == fault_key))
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fault not found in this version")
    edited = _pending_keys(session, v)
    items = {}
    for t in ITEM_TYPES:
        key = f"{fault_key}/{t}"
        items[t] = {
            "key": key,
            **HANDLERS["fault_items"].snapshot(session, v, key),
            "edit": edited.get(f"fault_items:{key}"),
        }
    phrases = []
    for p in session.scalars(
        select(CustomerPhrase).where(CustomerPhrase.fault_id == f.id).order_by(CustomerPhrase.source, CustomerPhrase.id)
    ):
        key = phrase_key(fault_key, p.text)
        phrases.append(
            {
                "key": key,
                "text": p.text,
                "language": str(p.language),
                "english_gloss": p.english_gloss or "",
                "source": str(p.source),
                "held_out": p.held_out,
                "reviewed_by": p.reviewed_by,
                "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
                "pending_signoff": p.source == PhraseSource.drafted and pending(p.reviewed_by),
                "edit": edited.get(f"phrase:{key}"),
            }
        )
    images = []
    for sha in HANDLERS["fault_images"].snapshot(session, v, fault_key)["images"]:
        img = session.scalar(select(Image).where(Image.sha1 == sha))
        images.append({"sha1": sha, "url": _media_url(img.path), "caption": img.caption})
    rules = []
    for r in session.scalars(select(SafetyRule).where(SafetyRule.fault_id == f.id).order_by(SafetyRule.id)):
        key = f"{fault_key}/{r.source}/{r.kind}"
        rules.append(
            {
                "key": key,
                "scope": str(r.scope),
                "source": str(r.source),
                "kind": str(r.kind),
                **HANDLERS["safety_rule"].snapshot(session, v, key),
                "edit": edited.get(f"safety_rule:{key}"),
            }
        )
    deleted = [
        {"key": e.key.split("|", 1)[1], "edit": e.id}
        for e in session.scalars(
            select(KnowledgeEdit).where(
                KnowledgeEdit.dataset_version_id == v.id,
                KnowledgeEdit.status == EditStatus.draft,
                KnowledgeEdit.entity == "phrase",
                KnowledgeEdit.key.like(f"{fault_key}|%"),
                KnowledgeEdit.data.is_(None),
            )
        )
    ]
    return {
        "key": fault_key,
        "fault": HANDLERS["fault"].snapshot(session, v, fault_key),
        "fault_edit": edited.get(f"fault:{fault_key}"),
        "items": items,
        "phrases": phrases,
        "deleted_phrases": deleted,
        "images": images,
        "images_edit": edited.get(f"fault_images:{fault_key}"),
        "safety_rules": rules,
        "file_no": f.source_file_no,
    }


@router.get("/versions/{version_id}/questions")
@requires(Perm.content_read)
def questions(version_id: int, session: DbSession, category: Annotated[str, Query()]):
    """The category's questions with answers and effects, and its faults (for the effect pickers)."""
    v = _version(session, version_id)
    edited = _pending_keys(session, v)
    out = []
    for q in session.scalars(
        select(Question)
        .where(Question.dataset_version_id == v.id, Question.category_code == category)
        .order_by(Question.stage, Question.id)
    ):
        if not q.ref:
            continue
        key = f"{category}/{q.ref}"
        snap = HANDLERS["question"].snapshot(session, v, key)
        out.append(
            {"key": key, **snap, "pending_signoff": pending(snap["reviewed_by"]), "edit": edited.get(f"question:{key}")}
        )
    faults_ = session.execute(
        select(Fault.fault_key, Fault.name)
        .where(Fault.dataset_version_id == v.id, Fault.category_code == category)
        .order_by(Fault.fault_key)
    ).all()
    return {"questions": out, "faults": [{"key": k, "name": n} for k, n in faults_]}


@router.get("/versions/{version_id}/safety")
@requires(Perm.content_read)
def safety_rules(version_id: int, session: DbSession):
    """Every live-able safety rule of the version: emergency (global) rules first, then fault rules."""
    v = _version(session, version_id)
    edited = _pending_keys(session, v)
    keys = dict(session.execute(select(Fault.id, Fault.fault_key).where(Fault.dataset_version_id == v.id)).all())
    cats = dict(session.execute(select(Fault.id, Fault.category_code).where(Fault.dataset_version_id == v.id)).all())
    out = []
    for r in session.scalars(
        select(SafetyRule).where(SafetyRule.dataset_version_id == v.id).order_by(SafetyRule.scope, SafetyRule.id)
    ):
        if str(r.scope) == "global":
            key = f"global/{r.source_ref}"
        elif r.fault_id in keys:
            key = f"{keys[r.fault_id]}/{r.source}/{r.kind}"
        else:
            continue
        out.append(
            {
                "key": key,
                "scope": str(r.scope),
                "category": cats.get(r.fault_id),
                "fault_key": keys.get(r.fault_id),
                "source": str(r.source),
                "kind": str(r.kind),
                "triggers_reviewed_by": (r.triggers or {}).get("reviewed_by"),
                **HANDLERS["safety_rule"].snapshot(session, v, key),
                "edit": edited.get(f"safety_rule:{key}"),
            }
        )
    return out


@router.get("/versions/{version_id}/signoff")
@requires(Perm.content_read)
def signoff_queue(version_id: int, session: DbSession):
    """Items still pending a person's sign-off (checked automatically: claude_code ... pending mechanic sign-off),
    and the ones signed off in this draft."""
    from app.vision.models import ImageLabel

    v = _version(session, version_id)
    edited = _pending_keys(session, v)
    keys = dict(session.execute(select(Fault.id, Fault.fault_key).where(Fault.dataset_version_id == v.id)).all())
    cats = dict(session.execute(select(Fault.id, Fault.category_code).where(Fault.dataset_version_id == v.id)).all())
    out = []
    for q in session.scalars(select(Question).where(Question.dataset_version_id == v.id, Question.ref.is_not(None))):
        key = f"{q.category_code}/{q.ref}"
        out.append(
            _queue_item("question", key, q.category_code, q.text_en, q.reviewed_by, pending(q.reviewed_by), edited)
        )
    for p in session.scalars(
        select(CustomerPhrase).where(
            CustomerPhrase.fault_id.in_(list(keys)), CustomerPhrase.source == PhraseSource.drafted
        )
    ):
        key = phrase_key(keys[p.fault_id], p.text)
        out.append(
            _queue_item(
                "phrase",
                key,
                cats[p.fault_id],
                f"{keys[p.fault_id]}: {p.text}",
                p.reviewed_by,
                pending(p.reviewed_by),
                edited,
            )
        )
    for r in session.scalars(select(SafetyRule).where(SafetyRule.dataset_version_id == v.id)):
        if str(r.scope) == "global":
            key, cat = f"global/{r.source_ref}", None
            todo = r.status == SafetyStatus.active_pending_signoff or pending((r.triggers or {}).get("reviewed_by"))
        elif r.fault_id in keys:
            key, cat = f"{keys[r.fault_id]}/{r.source}/{r.kind}", cats[r.fault_id]
            todo = r.status == SafetyStatus.active_pending_signoff
        else:
            continue
        what = (r.stop_driving_trigger or r.roadside_action or "")[:140]
        out.append(_queue_item("safety_rule", key, cat, f"{key}: {what}", r.signed_off_by, todo, edited))
    for lb in session.scalars(select(ImageLabel).order_by(ImageLabel.code)):
        out.append(
            _queue_item("image_label", lb.code, None, f"{lb.name} ({lb.mode})", lb.reviewed_by, not lb.reviewed, edited)
        )
    return out


def _queue_item(entity, key, category, text, reviewed_by, todo, edited) -> dict:
    edit = edited.get(f"{entity}:{key}")
    if entity == "image_label" and edit:
        todo = False  # photo labels are a live list: the draft's sign-off is applied at publish
    return {
        "entity": entity,
        "key": key,
        "category": category,
        "text": text,
        "reviewed_by": reviewed_by,
        "pending": bool(todo),
        "edit": edit,
    }


@router.get("/images")
@requires(Perm.content_read)
def images(session: DbSession, file_no: Annotated[int | None, Query(ge=1, le=99)] = None):
    """Pictures extracted from the datasets (for the media picker), optionally one file's."""
    q = select(Image).order_by(Image.path).limit(500)
    if file_no:
        q = q.where(Image.path.like(f"data/media/F{file_no:02d}/%"))
    return [{"sha1": i.sha1, "url": _media_url(i.path), "caption": i.caption} for i in session.scalars(q)]


# ---------------------------------------------------------------- edits


class EditIn(BaseModel):
    entity: str
    key: str = Field("", max_length=400, description="Empty for a new fault or question (the server picks it)")
    data: dict[str, Any] | None = Field(None, description="The item's full new state; null deletes it")
    reason: str = Field("", max_length=1000)


class SignOffIn(BaseModel):
    entity: str
    key: str


def _edit_out(session: Session, version: DatasetVersion, e: KnowledgeEdit | None, key: str, entity: str) -> dict:
    h = HANDLERS[entity]
    return {
        "key": key,
        "item": h.snapshot(session, version, key) if not h.global_table else (e.data if e else None),
        "edit": None if e is None else {"id": e.id, "safety": e.safety},
        "warning": SAFETY_WARNING if h.safety else None,
    }


def _new_key(session: Session, version: DatasetVersion, body: EditIn) -> str:
    data = body.data or {}
    if body.entity == "fault":
        code = data.get("category_code")
        tax = version_taxonomy(session, version, load_config().taxonomy)
        cat = next((c for c in tax["categories"] if c["code"] == code), None)
        if cat is None or not cat.get("sources"):
            raise Invalid("choose a category that has a source file")
        src = cat["sources"][0]
        return next_fault_key(session, version, src["file"], src["prefix"])
    if body.entity == "question":
        category = body.key.rstrip("/") or data.get("category")
        if not category:
            raise Invalid("a new question needs its category")
        n = (
            session.scalar(
                select(func.count()).where(Question.dataset_version_id == version.id, Question.ref.like("edit-%"))
            )
            or 0
        )
        existing = set(session.scalars(select(KnowledgeEdit.key).where(KnowledgeEdit.entity == "question")))
        while f"{category}/edit-{n + 1}" in existing:
            n += 1
        return f"{category}/edit-{n + 1}"
    if body.entity == "part":
        from app.knowledge.edits.parts_handlers import new_part_key

        return new_part_key(HANDLERS["part"].validate(data, exists=False))
    if body.entity == "part_price":  # key "<part key>|<segment>|": a new editor price
        from app.parts.models import PartPrice

        part_key, _, segment = body.key.rstrip("|").rpartition("|")
        n = (
            session.scalar(
                select(func.count()).where(
                    PartPrice.dataset_version_id == version.id, PartPrice.source_ref.like("editor-%")
                )
            )
            or 0
        )
        existing = set(session.scalars(select(KnowledgeEdit.key).where(KnowledgeEdit.entity == "part_price")))
        while f"{part_key}|{segment}|editor-{n + 1}" in existing:
            n += 1
        return f"{part_key}|{segment}|editor-{n + 1}"
    if body.entity == "part_fit":  # key "<part key>|": the rest comes from the fit itself
        from app.knowledge.edits.parts_handlers import fit_key

        return fit_key(body.key.rstrip("|"), HANDLERS["part_fit"].validate(data, exists=False))
    raise Invalid("every edit needs the item's key")


@router.post("/versions/{version_id}/edits", responses={404: {}, 409: {}, 422: {}})
@requires(Perm.knowledge_edit)
def save_edit(version_id: int, body: EditIn, staff: CurrentStaff, session: DbSession):
    """Save an item in the draft (create, change or delete). Validated like the forms; audited; a safety rule change
    is audited with its old and new values."""
    v = _version(session, version_id)
    if body.entity not in HANDLERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown item type {body.entity}")
    try:
        key = body.key
        if not key or (body.entity == "question" and key.endswith("/")) or key.endswith("|"):
            key = _new_key(session, v, body)
        data = body.data
        if body.entity == "question" and data:
            data = {k: val for k, val in data.items() if k != "category"}
        e = service.save(session, v, _actor(staff), body.entity, key, data, body.reason)
    except Orphan as e:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{e} is not in this draft") from e
    except (Invalid, ValueError) as e:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _message(e)) from e
    session.commit()
    out = _edit_out(session, v, e, key, body.entity)
    if body.entity == "part_price" and out["item"]:
        from app.knowledge.edits.parts_handlers import SECOND_LOOK_INR, needs_second_look

        if needs_second_look(out["item"]):
            out["warning"] = (
                f"This price is {SECOND_LOOK_INR:,} rupees or more: it is flagged until a second person checks it "
                "(Parts & Prices, Prices, 'Second look')."
            )
    if untriggered := getattr(HANDLERS[body.entity], "untriggered", None):
        out["warning"] = (
            "Removed answers were safety triggers; those safety rules no longer fire on them: " + "; ".join(untriggered)
        )
    return out


def _message(e: Exception) -> str:
    errors = getattr(e, "errors", None)
    if callable(errors):  # pydantic ValidationError
        return "; ".join(f"{'.'.join(map(str, x['loc'])) or 'item'}: {x['msg']}" for x in errors())
    return str(e)


@router.post("/versions/{version_id}/signoff", responses={404: {}, 422: {}})
@requires(Perm.knowledge_edit)
def sign_off(version_id: int, body: SignOffIn, staff: CurrentStaff, session: DbSession):
    """Mark an item as reviewed under your name and today's date (a safety rule becomes approved)."""
    v = _version(session, version_id)
    try:
        e = service.sign_off(session, v, _actor(staff), body.entity, body.key)
    except (Invalid, ValueError) as e:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _message(e)) from e
    session.commit()
    return _edit_out(session, v, e, body.key, body.entity)


class BulkSignOffIn(BaseModel):
    items: list[SignOffIn] = Field(min_length=1, max_length=service.BULK_LIMIT)
    filter: dict[str, Any] = Field(default_factory=dict, description="The filter that selected them (for the audit)")


@router.post("/versions/{version_id}/signoff/bulk", responses={404: {}, 422: {}})
@requires(Perm.knowledge_edit)
def bulk_sign_off(version_id: int, body: BulkSignOffIn, staff: CurrentStaff, session: DbSession):
    """Sign off every listed item under your name and today's date: one audit entry with the count and the filter."""
    v = _version(session, version_id)
    try:
        service.editable(v)
        out = service.bulk_sign_off(session, v, _actor(staff), [(i.entity, i.key) for i in body.items], body.filter)
    except (Invalid, ValueError) as e:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _message(e)) from e
    session.commit()
    return out


@router.get("/versions/{version_id}/edits")
@requires(Perm.content_read)
def list_edits(version_id: int, session: DbSession):
    """This draft's edits (newest first), the per-table summary and every safety change by name, plus conflicts and
    edits that could not be applied when the draft was last built."""
    v = _version(session, version_id)
    rows = []
    for e in reversed(service.draft_edits(session, v)):
        h = HANDLERS[e.entity]
        fields = changed_fields(e.base, e.data)
        rows.append(
            {
                "id": e.id,
                "entity": e.entity,
                "table": h.label,
                "key": e.key,
                "name": h.name(e.key, e.data, e.base),
                "op": "signed off"
                if e.signoff
                else "added"
                if e.base is None
                else "deleted"
                if e.data is None
                else "changed",
                "safety": e.safety,
                "status": str(e.status),
                "by": e.created_by,
                "at": e.updated_at.isoformat(),
                "reason": e.reason,
                "changes": [
                    {"field": f, "before": (e.base or {}).get(f), "after": (e.data or {}).get(f)} for f in fields
                ],
            }
        )
    applied = ((v.validation or {}).get("steps") or {}).get("edits") or {}
    return {
        "edits": rows,
        "summary": service.summary(session, v),
        "conflicts": applied.get("conflicts", []),
        "orphans": applied.get("orphans", []),
    }


@router.delete(
    "/versions/{version_id}/edits/{edit_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {}, 422: {}}
)
@requires(Perm.knowledge_edit)
def revert_edit(version_id: int, edit_id: int, staff: CurrentStaff, session: DbSession):
    """Undo a pending edit of this draft (the item goes back to how it was)."""
    v = _version(session, version_id)
    e = session.get(KnowledgeEdit, edit_id)
    if e is None or e.dataset_version_id != v.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Edit not found")
    try:
        service.revert(session, v, _actor(staff), e)
    except Invalid as err:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
    session.commit()


# ---------------------------------------------------------------- generated questions (review queue)


class GeneratedApproveIn(BaseModel):
    version_id: int
    category: str
    stage: int = Field(3, ge=2, le=9)
    text: str = Field(min_length=3, max_length=400)
    options: list[str] = Field(min_length=2, max_length=10)


@router.post("/generated-questions/{question_id}/approve", responses={404: {}, 409: {}, 422: {}})
@requires(Perm.knowledge_edit)
def approve_generated(question_id: int, body: GeneratedApproveIn, staff: CurrentStaff, session: DbSession):
    """Approve a question the LLM proposed (after editing it): it is added to the draft as a new question with a
    'Not sure' answer. Its answers have no effects yet: add them in the question editor."""
    g = session.get(GeneratedQuestion, question_id)
    if g is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    if g.status != GeneratedStatus.generated:
        raise HTTPException(status.HTTP_409_CONFLICT, "This question was already reviewed")
    v = _version(session, body.version_id)
    labels = [o.strip() for o in body.options if o.strip() and o.strip().lower() != "not sure"]
    data = {
        "stage": body.stage,
        "text": body.text,
        "status": "approved",
        "reviewed_by": staff.label,
        "reviewed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "options": [
            *({"label": o, "not_sure": False, "effects": []} for o in labels),
            {"label": "Not sure", "not_sure": True, "effects": []},
        ],
    }
    try:
        key = _new_key(session, v, EditIn(entity="question", key=f"{body.category}/"))
        service.save(session, v, _actor(staff), "question", key, data, f"approved LLM question {g.id}")
    except (Invalid, ValueError) as e:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _message(e)) from e
    before = {"status": str(g.status), "text": g.text, "options": g.options}
    g.status, g.reviewed_by, g.reviewed_at = GeneratedStatus.approved, staff.label, datetime.now(UTC)
    g.text, g.options = body.text, labels
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="content.review_question",
        entity_type="generated_question",
        entity_id=g.id,
        before=before,
        after={"status": "approved", "text": body.text, "options": labels, "draft": v.id, "question": key},
        ip=staff.ip,
    )
    session.commit()
    return {"question": key, "version_id": v.id}
