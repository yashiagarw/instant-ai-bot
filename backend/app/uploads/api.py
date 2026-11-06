"""Photo uploads. Only the owner of the diagnosis session may add, see or delete its photos; anyone else is told the
upload or session does not exist (404). Photos are never public: GET answers a signed link valid a few minutes.

1. POST /api/uploads                 -> a presigned POST form (the storage refuses files over the size limit)
2. the browser posts the file straight to the storage
3. POST /api/uploads/{id}/complete   -> the API checks the real type, size and pixels, re-encodes, keeps the clean JPEG
4. GET  /api/uploads/{id}            -> a short-lived signed link, for the owner only
5. POST /api/uploads/{id}/analyze    -> what the photo may show (app.vision), never blocking the diagnosis
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts import service as accounts
from app.accounts.service import ANON_COOKIE, SESSION_COOKIE
from app.db import get_session
from app.diagnosis import service as diagnosis_service
from app.diagnosis.models import DiagnosisSession
from app.diagnosis.schemas import SafetyAlertOut
from app.ratelimit import client_ip, make_limiter
from app.uploads.imaging import MESSAGES, ImageRejected, process
from app.uploads.models import Upload, UploadStatus
from app.uploads.storage import Storage, StorageError, make_storage
from app.vision import analysis
from app.vision.models import AnalysisMode, FindingStatus, ImageFinding

log = logging.getLogger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])
DbSession = Annotated[Session, Depends(get_session)]
DECLARED = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
NOT_FOUND = "Photo not found"
STORAGE_DOWN = "We couldn't reach our photo storage. Please try again, or carry on without a photo."


def get_storage(request: Request) -> Storage:
    state = request.app.state
    if getattr(state, "storage", None) is None:
        state.storage = make_storage(state.settings)
    return state.storage


StorageDep = Annotated[Storage, Depends(get_storage)]


def limit_uploads(request: Request) -> None:
    state = request.app.state
    s = state.settings
    if getattr(state, "upload_limiter", None) is None:
        state.upload_limiter = make_limiter(s, "uploads", s.upload_rate_limit, s.upload_rate_window_seconds)
    wait = state.upload_limiter.check(client_ip(request, s.trust_forwarded_for))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many photos from this network. Please wait a little and try again.",
            headers={"Retry-After": str(max(1, round(wait)))},
        )


class Caller:
    def __init__(self, request: Request, session: DbSession):
        self.user = accounts.current_user(session, request.cookies.get(SESSION_COOKIE))
        self.anon = request.cookies.get(ANON_COOKIE)

    def owns(self, row: DiagnosisSession | Upload) -> bool:
        return accounts.owns(row, self.user, self.anon)


CallerDep = Annotated[Caller, Depends(Caller)]


class UploadIn(BaseModel):
    session_id: uuid.UUID
    content_type: str = Field(description="What the browser says the file is (checked again from the bytes).")
    size: int = Field(gt=0, description="File size in bytes.")


class UploadFormOut(BaseModel):
    upload_id: uuid.UUID
    url: str = Field(description="POST the file here as multipart/form-data, with `fields` first and `file` last.")
    fields: dict[str, str]
    max_bytes: int
    expires_in: int


class AnalyzeIn(BaseModel):
    mode: AnalysisMode = Field(description="warning_light: a dashboard light. damage: visible damage, wear or a leak.")


class FindingLabelOut(BaseModel):
    code: str
    name: str
    meaning: str
    severity: str | None = Field(default=None, description="Warning lights: red, amber or info.")
    confidence: float
    reviewed: bool = Field(description="False until a mechanic has reviewed this label.")


class FindingOut(BaseModel):
    upload_id: uuid.UUID
    mode: AnalysisMode
    status: FindingStatus = Field(description="found, unclear (retake), unavailable or failed (a mechanic looks).")
    message: str
    labels: list[FindingLabelOut] = Field(description='Shown as "Possible: ..."; never a verified fact.')
    safety: list[SafetyAlertOut] = Field(description="Safety rules for a red light or dangerous damage.")


class PhotoOut(BaseModel):
    id: uuid.UUID
    status: UploadStatus
    width: int | None = None
    height: int | None = None
    url: str | None = Field(default=None, description="Signed link, valid `expires_in` seconds, owner only.")
    expires_in: int | None = None
    findings: list[FindingOut] = Field(default_factory=list)


def _owned_upload(session: Session, caller: Caller, upload_id: uuid.UUID) -> Upload:
    row = session.get(Upload, upload_id)
    if row is None or not caller.owns(row):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return row


def _finding_out(session: Session, finding: ImageFinding) -> FindingOut:
    views = analysis.label_views(session, finding)
    return FindingOut(
        upload_id=finding.upload_id,
        mode=finding.mode,
        status=finding.status,
        message=analysis.MESSAGES[finding.status],
        labels=[FindingLabelOut(**{k: getattr(v, k) for k in FindingLabelOut.model_fields}) for v in views],
        safety=[SafetyAlertOut(**a) for a in analysis.safety_alerts(session, finding, views)],
    )


def _photo_out(request: Request, storage: Storage, row: Upload, session: Session | None = None) -> PhotoOut:
    ttl = request.app.state.settings.upload_view_ttl_seconds
    url = storage.presign_view(row.object_key, ttl) if row.status == UploadStatus.ready else None
    findings = []
    if session is not None:
        rows = session.scalars(select(ImageFinding).where(ImageFinding.upload_id == row.id).order_by(ImageFinding.id))
        findings = [_finding_out(session, f) for f in rows]
    return PhotoOut(
        id=row.id,
        status=row.status,
        width=row.width,
        height=row.height,
        url=url,
        expires_in=ttl if url else None,
        findings=findings,
    )


@router.post(
    "",
    response_model=UploadFormOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_uploads)],
    responses={404: {"description": "Session not found"}, 409: {}, 422: {}, 429: {}, 503: {}},
)
def create_upload(
    body: UploadIn, request: Request, response: Response, session: DbSession, caller: CallerDep, storage: StorageDep
):
    """A presigned form to send one photo (JPEG, PNG, WebP or HEIC, at most UPLOAD_MAX_BYTES) for your session."""
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    ds = session.get(DiagnosisSession, body.session_id)
    if ds is None or not caller.owns(ds):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if body.content_type.lower() not in DECLARED:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, MESSAGES["wrong_type"])
    if body.size > settings.upload_max_bytes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, MESSAGES["too_large"])
    used = session.scalar(
        select(func.count())
        .select_from(Upload)
        .where(Upload.session_id == ds.id, Upload.status != UploadStatus.rejected)
    )
    if used >= settings.uploads_per_session:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"You can add up to {settings.uploads_per_session} photos to one diagnosis."
        )
    row = Upload(session_id=ds.id, user_id=ds.user_id, anon_key_hash=ds.anon_key_hash, declared_type=body.content_type)
    session.add(row)
    session.flush()
    try:
        form = storage.presign_upload(row.incoming_key, settings.upload_max_bytes, settings.upload_url_ttl_seconds)
    except StorageError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, STORAGE_DOWN) from e
    session.commit()
    return UploadFormOut(
        upload_id=row.id, max_bytes=settings.upload_max_bytes, expires_in=settings.upload_url_ttl_seconds, **form
    )


@router.post(
    "/{upload_id}/complete",
    response_model=PhotoOut,
    responses={404: {}, 409: {"description": "Not uploaded yet, or already checked"}, 422: {}, 503: {}},
)
def complete_upload(
    upload_id: uuid.UUID,
    request: Request,
    response: Response,
    session: DbSession,
    caller: CallerDep,
    storage: StorageDep,
):
    """Check the uploaded file and keep a clean copy: the real type from its bytes (JPEG, PNG, WebP, HEIC), at most
    10 MB, re-encoded as JPEG, at most 2000 px, with no EXIF, GPS or other metadata. The raw upload is deleted."""
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    row = _owned_upload(session, caller, upload_id)
    if row.status != UploadStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "This photo has already been checked")
    try:
        size = storage.size(row.incoming_key)
        if size is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "The photo has not arrived yet. Please send it again.")
        try:
            if size > settings.upload_max_bytes:
                raise ImageRejected("too_large")
            clean = process(storage.get(row.incoming_key), settings.upload_max_bytes, settings.upload_max_px)
        except ImageRejected as e:
            row.status, row.reject_reason, row.original_bytes = UploadStatus.rejected, e.code, size
            row.completed_at = datetime.now(UTC)
            storage.delete([row.incoming_key])
            session.commit()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        storage.put(row.object_key, clean.data, "image/jpeg")
        storage.delete([row.incoming_key])
    except StorageError as e:
        session.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, STORAGE_DOWN) from e
    row.status, row.detected_type = UploadStatus.ready, clean.source_type
    row.original_bytes, row.stored_bytes, row.width, row.height = size, len(clean.data), clean.width, clean.height
    row.completed_at = datetime.now(UTC)
    session.commit()
    return _photo_out(request, storage, row)


@router.get("/{upload_id}", response_model=PhotoOut, responses={404: {}})
def get_upload(
    upload_id: uuid.UUID,
    request: Request,
    response: Response,
    session: DbSession,
    caller: CallerDep,
    storage: StorageDep,
):
    """The photo's details and a signed link to it (a few minutes). Owner only."""
    response.headers["Cache-Control"] = "no-store"
    return _photo_out(request, storage, _owned_upload(session, caller, upload_id), session)


@router.get("", response_model=list[PhotoOut], responses={404: {}})
def list_uploads(
    request: Request,
    response: Response,
    session: DbSession,
    caller: CallerDep,
    storage: StorageDep,
    session_id: Annotated[uuid.UUID, Query()],
):
    """Your ready photos for one diagnosis session."""
    response.headers["Cache-Control"] = "no-store"
    ds = session.get(DiagnosisSession, session_id)
    if ds is None or not caller.owns(ds):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    rows = session.scalars(
        select(Upload)
        .where(Upload.session_id == ds.id, Upload.status == UploadStatus.ready)
        .order_by(Upload.created_at)
    ).all()
    return [_photo_out(request, storage, r, session) for r in rows if caller.owns(r)]


@router.post(
    "/{upload_id}/analyze",
    response_model=FindingOut,
    dependencies=[Depends(limit_uploads)],
    responses={404: {}, 409: {"description": "The photo is not checked yet"}, 503: {}},
)
def analyze_upload(
    upload_id: uuid.UUID,
    body: AnalyzeIn,
    request: Request,
    response: Response,
    session: DbSession,
    caller: CallerDep,
    storage: StorageDep,
):
    """What the photo may show, from a fixed list only: a warning light (name, meaning, severity) or visible damage,
    or "unclear". Without a vision provider: status unavailable (no call, no cost); the photo is kept for the
    mechanic either way. A finding already made for this photo and mode is returned as it is (no second call)."""
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    row = _owned_upload(session, caller, upload_id)
    if row.status != UploadStatus.ready:
        raise HTTPException(status.HTTP_409_CONFLICT, "This photo has not been checked yet")
    done = session.scalar(
        select(ImageFinding).where(
            ImageFinding.upload_id == row.id,
            ImageFinding.mode == body.mode,
            ImageFinding.status.in_([FindingStatus.found, FindingStatus.unclear]),
        )
    )
    if done is None:
        llm = diagnosis_service.get_llm(request.app.state)
        image = None
        if llm is not None:
            try:
                image = storage.get(row.object_key)
            except StorageError as e:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, STORAGE_DOWN) from e
        done = analysis.analyze(session, row, body.mode, image, llm, settings.vision_min_confidence)
        session.commit()
    return _finding_out(session, done)


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {}, 503: {}})
def delete_upload(upload_id: uuid.UUID, session: DbSession, caller: CallerDep, storage: StorageDep):
    """Remove a photo (the stored objects and the row)."""
    row = _owned_upload(session, caller, upload_id)
    try:
        storage.delete([row.incoming_key, row.object_key])
    except StorageError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, STORAGE_DOWN) from e
    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
