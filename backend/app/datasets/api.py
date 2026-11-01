"""/api/admin/datasets: the admin Datasets page (upload a category file, validation report, diff, eval, publish,
discard, roll back). Its own router with the same deny-by-default access check as the rest of /api/admin
(check_admin_routes covers both). The work runs in the background worker; these endpoints create jobs and read state.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.permissions import Perm
from app.datasets import jobs
from app.datasets.pipeline import live_version, publish_blockers
from app.db import get_session
from app.knowledge.importer.config import REPO_ROOT, load_config
from app.knowledge.models import (
    Category,
    DatasetJob,
    DatasetOrigin,
    DatasetStatus,
    DatasetVersion,
    JobKind,
    JobStatus,
)

router = APIRouter(prefix="/admin/datasets", tags=["admin"], dependencies=[Depends(enforce)])
DbSession = Annotated[Session, Depends(get_session)]
XLSX_MAGIC = b"PK\x03\x04"  # an .xlsx file is a zip archive
MIN_OVERRIDE_REASON = 15  # characters


# ---------------------------------------------------------------- schemas


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    progress: int
    step: str
    log: list[dict]
    error: str | None
    result: dict
    dataset_version_id: int | None
    created_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class VersionOut(BaseModel):
    id: int
    status: str
    origin: str
    category_code: str | None
    source_file_no: int | None
    upload_name: str | None
    created_by: str | None
    created_at: datetime
    published_at: datetime | None
    published_by: str | None
    archived_at: datetime | None
    base_version_id: int | None
    rollback_of_id: int | None
    override_reason: str | None
    categories: list[str] = Field(description="Categories whose rows this version changes (from its file).")
    stale: bool = Field(description="A draft built on a version that is no longer the published one.")
    validated: bool | None = Field(description="null until built (or when the build failed)")
    build_error: str | None
    losses: int
    diff_counts: dict[str, int]
    gate: Literal["passed", "blocked"] | None
    gate_reasons: list[str]


class PublishState(BaseModel):
    blockers: list[str] = Field(description="Problems nothing can override.")
    gate_reasons: list[str] = Field(description="Eval gate reasons: a super_admin may override with a reason.")
    can_publish: bool
    can_override: bool


class VersionDetail(VersionOut):
    validation: dict
    diff: dict
    eval: dict
    publish: PublishState
    jobs: list[JobOut]


class CategoryFile(BaseModel):
    file_no: int
    live_name: str = Field(description="The file the live version was built from.")


class CategoryOut(BaseModel):
    code: str
    name: str
    files: list[CategoryFile]
    shared_with: list[str] = Field(description="Other categories in the same file(s): an upload changes them too.")


class OverviewOut(BaseModel):
    live: VersionOut | None
    versions: list[VersionOut]
    categories: list[CategoryOut]
    active_job: JobOut | None
    can_manage: bool
    can_override: bool


class EvalIn(BaseModel):
    full: bool = Field(False, description="Every case of every category (slow) instead of the affected test split.")


class PublishIn(BaseModel):
    override_reason: str | None = Field(None, max_length=2000)


class CreatedOut(BaseModel):
    version: VersionOut
    job: JobOut


# ---------------------------------------------------------------- helpers


def _job_out(j: DatasetJob) -> JobOut:
    return JobOut(
        id=j.id, kind=str(j.kind), status=str(j.status), progress=j.progress, step=j.step, log=list(j.log or []),
        error=j.error, result=dict(j.result or {}), dataset_version_id=j.dataset_version_id, created_by=j.created_by,
        created_at=j.created_at, started_at=j.started_at, finished_at=j.finished_at,
    )  # fmt: skip


def _version_out(v: DatasetVersion, live: DatasetVersion | None) -> VersionOut:
    val, diff, ev = v.validation or {}, v.diff or {}, v.eval or {}
    checks = val.get("checks")
    gate = ev.get("gate")
    return VersionOut(
        id=v.id, status=str(v.status), origin=str(v.origin), category_code=v.category_code,
        source_file_no=v.source_file_no, upload_name=v.upload_name, created_by=v.created_by, created_at=v.created_at,
        published_at=v.published_at, published_by=v.published_by, archived_at=v.archived_at,
        base_version_id=v.base_version_id, rollback_of_id=v.rollback_of_id, override_reason=v.override_reason,
        categories=list(val.get("categories") or ([v.category_code] if v.category_code else [])),
        stale=(
            v.status in (DatasetStatus.draft, DatasetStatus.validated)
            and v.origin != DatasetOrigin.import_
            and live is not None
            and live.status == DatasetStatus.published
            and v.base_version_id != live.id
        ),
        validated=None if not checks else all(c["ok"] for c in checks if c["blocking"]),
        build_error=val.get("error"),
        losses=len(val.get("losses") or []),
        diff_counts={k: len(diff.get(k) or []) for k in ("added", "changed", "removed")},
        gate=None if gate is None else ("passed" if gate["ok"] else "blocked"),
        gate_reasons=list((gate or {}).get("reasons") or []),
    )  # fmt: skip


def _version_or_404(session: Session, version_id: int) -> DatasetVersion:
    v = session.get(DatasetVersion, version_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset version not found")
    return v


def _queue(request: Request) -> jobs.JobQueue:
    queue = getattr(request.app.state, "job_queue", None)
    if queue is None:
        queue = request.app.state.job_queue = jobs.ArqQueue(request.app.state.settings.redis_url)
    return queue


def _start(
    request: Request,
    session: Session,
    staff,
    kind: JobKind,
    version: DatasetVersion,
    action: str,
    params: dict | None = None,
    before: dict | None = None,
) -> DatasetJob:
    """Create the job and its audit row, commit, then put it on the queue."""
    try:
        job = jobs.create_job(session, kind, version.id, staff.user.id, staff.label, params)
    except jobs.JobBusy as e:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action=action,
        entity_type="dataset_version",
        entity_id=version.id,
        before=before,
        after={"job": job.id, **{k: v for k, v in (params or {}).items() if k != "override_reason"}},
        ip=staff.ip,
    )
    session.commit()
    try:
        _queue(request).enqueue(job.id)
    except jobs.QueueUnavailable as e:
        job.status, job.error = JobStatus.failed, "Background jobs are not running."
        session.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Background jobs are not running: start Redis (docker compose up -d redis) and the worker "
            "(cd backend && uv run arq app.datasets.worker.WorkerSettings), then try again.",
        ) from e
    return job


def _detail(session: Session, v: DatasetVersion, staff) -> VersionDetail:
    live = live_version(session)
    hard, reasons = publish_blockers(session, v) if v.status == DatasetStatus.validated else ([], [])
    can_override = Perm.datasets_override in staff.perms
    recent = session.scalars(
        select(DatasetJob).where(DatasetJob.dataset_version_id == v.id).order_by(DatasetJob.id.desc()).limit(10)
    )
    return VersionDetail(
        **_version_out(v, live).model_dump(),
        validation=v.validation or {},
        diff=v.diff or {},
        eval=v.eval or {},
        publish=PublishState(
            blockers=hard if v.status == DatasetStatus.validated else ["Only a validated draft can be published."],
            gate_reasons=reasons,
            can_publish=v.status == DatasetStatus.validated and not hard and (not reasons or can_override),
            can_override=can_override,
        ),
        jobs=[_job_out(j) for j in recent],
    )


def _safe_name(name: str) -> str:
    base = Path(name or "upload.xlsx").name
    return re.sub(r"[^A-Za-z0-9 ._&()-]", "_", base)[:120] or "upload.xlsx"


async def _raw_body(request: Request) -> bytes:
    """The uploaded file (request body), refused above DATASET_UPLOAD_MAX_MB."""
    limit = request.app.state.settings.dataset_upload_max_mb * 1024 * 1024
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"The file is larger than {limit // 2**20} MB")
    return bytes(data)


# ---------------------------------------------------------------- read


@router.get("", response_model=OverviewOut)
@requires(Perm.content_read)
def overview(staff: CurrentStaff, session: DbSession):
    """The live version, every version (newest first), the categories and their files, and the active job."""
    live = live_version(session)
    config = load_config()
    names = dict(session.execute(select(Category.code, Category.name)).all())
    live_files = (live.report.get("files") or {}) if live else {}
    by_category: dict[str, list[int]] = {}
    for n, entry in sorted(config.files.items()):
        for code in entry.categories.values():
            by_category.setdefault(code, []).append(n)
    categories = [
        CategoryOut(
            code=code,
            name=names.get(code, code),
            files=[
                CategoryFile(file_no=n, live_name=Path(live_files.get(str(n), {}).get("path") or "").name or "-")
                for n in files
            ],
            shared_with=sorted({c for n in files for c in config.files[n].categories.values()} - {code}),
        )
        for code, files in sorted(by_category.items(), key=lambda kv: names.get(kv[0], kv[0]))
    ]
    versions = session.scalars(select(DatasetVersion).order_by(DatasetVersion.id.desc()).limit(200)).all()
    active = session.scalar(
        select(DatasetJob)
        .where(DatasetJob.status.in_([JobStatus.queued, JobStatus.running]))
        .order_by(DatasetJob.id.desc())
    )
    return OverviewOut(
        live=_version_out(live, live) if live else None,
        versions=[_version_out(v, live) for v in versions],
        categories=categories,
        active_job=_job_out(active) if active else None,
        can_manage=Perm.datasets_manage in staff.perms,
        can_override=Perm.datasets_override in staff.perms,
    )


@router.get("/versions/{version_id}", response_model=VersionDetail, responses={404: {}})
@requires(Perm.content_read)
def get_version(version_id: int, staff: CurrentStaff, session: DbSession):
    """Validation report, diff against the version it was built on, eval comparison and whether it can be published."""
    return _detail(session, _version_or_404(session, version_id), staff)


@router.get("/jobs/{job_id}", response_model=JobOut, responses={404: {}})
@requires(Perm.content_read)
def get_job(job_id: int, session: DbSession):
    job = session.get(DatasetJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return _job_out(job)


# ---------------------------------------------------------------- write


@router.post(
    "/uploads",
    response_model=CreatedOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {}, 413: {}, 422: {}, 503: {}},
)
@requires(Perm.datasets_manage)
def upload(
    request: Request,
    staff: CurrentStaff,
    session: DbSession,
    data: Annotated[bytes, Depends(_raw_body)],
    category: Annotated[str, Query(description="Category code, e.g. brakes")],
    name: Annotated[str, Query(description="The file's name, e.g. BRAKES CATEGORY 11.xlsx")] = "upload.xlsx",
    file_no: Annotated[int | None, Query(description="Which source file, for a category fed by two")] = None,
):
    """Upload a new version of a category's Excel file (the request body). It becomes a draft built in the
    background: the other categories are copied from the published version."""
    config = load_config()
    files = [n for n, e in sorted(config.files.items()) if category in e.categories.values()]
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown category '{category}'")
    if file_no is None and len(files) > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"This category comes from files {', '.join(map(str, files))}: choose which one you are replacing.",
        )
    file_no = file_no if file_no is not None else files[0]
    if file_no not in files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"File {file_no} does not feed '{category}'")
    if not name.lower().endswith(".xlsx") or not data.startswith(XLSX_MAGIC):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Upload an Excel file (.xlsx)")
    live = live_version(session)
    if live is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Import the datasets once first (python -m app.knowledge.importer)"
        )

    settings = request.app.state.settings
    sha = hashlib.sha256(data).hexdigest()
    folder: Path = settings.dataset_upload_dir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha}.xlsx"
    if not path.exists():
        path.write_bytes(data)
    stored = str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)
    version = DatasetVersion(
        checksum="pending",
        status=DatasetStatus.draft,
        origin=DatasetOrigin.upload,
        category_code=category,
        source_file_no=file_no,
        base_version_id=live.id,
        upload_name=_safe_name(name),
        created_by=staff.label,
        validation={"upload": {"path": stored, "sha256": sha, "size": len(data), "name": _safe_name(name)}},
    )
    session.add(version)
    session.flush()
    job = _start(request, session, staff, JobKind.build, version, "dataset.upload", {"category": category,
                 "file_no": file_no, "sha256": sha})  # fmt: skip
    return CreatedOut(version=_version_out(version, live), job=_job_out(job))


@router.post("/versions/{version_id}/rebuild", response_model=JobOut, status_code=202, responses={404: {}, 409: {}})
@requires(Perm.datasets_manage)
def rebuild(version_id: int, request: Request, staff: CurrentStaff, session: DbSession):
    """Build the draft again on the version published now (after another category was published, or a failure)."""
    v = _version_or_404(session, version_id)
    if v.status not in (DatasetStatus.draft, DatasetStatus.validated) or v.origin == DatasetOrigin.import_:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an uploaded draft can be rebuilt.")
    live = live_version(session)
    before = {"base_version_id": v.base_version_id}
    v.base_version_id, v.status, v.eval = (live.id if live else None), DatasetStatus.draft, {}
    return _job_out(_start(request, session, staff, JobKind.build, v, "dataset.rebuild", before=before))


@router.post("/versions/{version_id}/eval", response_model=JobOut, status_code=202, responses={404: {}, 409: {}})
@requires(Perm.datasets_manage)
def run_eval(version_id: int, body: EvalIn, request: Request, staff: CurrentStaff, session: DbSession):
    """Evaluate the draft and the live version (test split of the affected categories, or everything)."""
    v = _version_or_404(session, version_id)
    if v.status != DatasetStatus.validated:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a validated draft can be evaluated.")
    return _job_out(_start(request, session, staff, JobKind.eval, v, "dataset.eval", {"full": body.full}))


@router.post(
    "/versions/{version_id}/publish", response_model=JobOut, status_code=202, responses={403: {}, 404: {}, 409: {}}
)
@requires(Perm.datasets_manage)
def publish(version_id: int, body: PublishIn, request: Request, staff: CurrentStaff, session: DbSession):
    """Publish the draft (in the background: the steps run again, nothing may be lost, then the switch). Blocked by
    the eval gate unless a super_admin gives a written reason."""
    v = _version_or_404(session, version_id)
    hard, reasons = publish_blockers(session, v)
    if hard:
        raise HTTPException(status.HTTP_409_CONFLICT, " ".join(hard))
    reason = (body.override_reason or "").strip()
    if reasons:
        if not reason:
            raise HTTPException(status.HTTP_409_CONFLICT, "Publishing is blocked: " + " ".join(reasons))
        if Perm.datasets_override not in staff.perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a super admin can override the eval gate.")
        if len(reason) < MIN_OVERRIDE_REASON:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Write why you are overriding (at least {MIN_OVERRIDE_REASON} characters).",
            )
    params = {"override_reason": reason} if reasons else {}
    job = _start(
        request, session, staff, JobKind.publish, v, "dataset.publish_requested", params,
        before={"gate": reasons, "override_reason": reason or None},
    )  # fmt: skip
    return _job_out(job)


class RollbackIn(BaseModel):
    category: str | None = Field(
        None, description="The category to restore (default: the one this version changed; all files for an import)."
    )


@router.post("/versions/{version_id}/rollback", response_model=JobOut, status_code=202, responses={404: {}, 409: {}})
@requires(Perm.datasets_manage)
def rollback(
    version_id: int, request: Request, staff: CurrentStaff, session: DbSession, body: RollbackIn | None = None
):
    """Restore a category as it was in this archived version. A new version is built from the live files with that
    category's file swapped back and published; other categories keep their current data."""
    v = _version_or_404(session, version_id)
    if v.status != DatasetStatus.archived:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an archived version can be rolled back to.")
    category = body.category if body else None
    if category and not any(category in e.categories.values() for e in load_config().files.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown category '{category}'")
    params = {"category": category} if category else {}
    return _job_out(_start(request, session, staff, JobKind.rollback, v, "dataset.rollback_requested", params))


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {}, 409: {}})
@requires(Perm.datasets_manage)
def discard(version_id: int, staff: CurrentStaff, session: DbSession, request: Request):
    """Delete a draft (its rows go with it; the uploaded file too unless another version uses it)."""
    v = _version_or_404(session, version_id)
    if v.status not in (DatasetStatus.draft, DatasetStatus.validated) or v.origin == DatasetOrigin.import_:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an uploaded draft can be discarded.")
    busy = session.scalar(
        select(func.count()).where(
            DatasetJob.dataset_version_id == v.id, DatasetJob.status.in_([JobStatus.queued, JobStatus.running])
        )
    )
    if busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "A job is running on this draft. Wait for it to finish.")
    upload = (v.validation or {}).get("upload") or {}
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="dataset.discard",
        entity_type="dataset_version",
        entity_id=v.id,
        before={"status": str(v.status), "category": v.category_code, "file": v.upload_name},
        after=None,
        ip=staff.ip,
    )
    session.delete(v)
    session.flush()
    if upload.get("sha256"):
        others = session.scalars(select(DatasetVersion.validation)).all()
        if not any(((o or {}).get("upload") or {}).get("sha256") == upload["sha256"] for o in others):
            path = request.app.state.settings.dataset_upload_dir / f"{upload['sha256']}.xlsx"
            path.unlink(missing_ok=True)
    session.commit()


@router.post("/jobs/{job_id}/cancel", response_model=JobOut, responses={404: {}, 409: {}})
@requires(Perm.datasets_manage)
def cancel_job(job_id: int, staff: CurrentStaff, session: DbSession):
    """Cancel a job the worker has not started (e.g. the worker is not running)."""
    job = session.get(DatasetJob, job_id, with_for_update=True)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job.status != JobStatus.queued:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a job that has not started can be cancelled.")
    job.status, job.error, job.finished_at = JobStatus.failed, f"Cancelled by {staff.label}", func.now()
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="dataset.job_cancel",
        entity_type="dataset_job",
        entity_id=job.id,
        before={"status": "queued", "kind": str(job.kind)},
        after={"status": "failed"},
        ip=staff.ip,
    )
    session.commit()
    session.refresh(job)
    return _job_out(job)
