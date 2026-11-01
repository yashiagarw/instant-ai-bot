"""Pictures uploaded in the admin app (fault and part pictures), through the customer-photo storage (SeaweedFS, S3)
and its checks (app.uploads.imaging): the real type from the bytes, at most UPLOAD_MAX_BYTES, re-encoded as JPEG,
at most UPLOAD_MAX_PX, no EXIF / GPS. The API receives the file (the storage only accepts browser uploads from the
website), keeps it under incoming/ (expired after a day if anything fails), then stores the clean copy as
media/uploaded/<sha1>.jpg. Pictures are served at /media/uploaded/<sha1>.jpg (a short-lived link to the private
bucket), so the website shows them like the pictures extracted from the datasets."""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.permissions import Perm
from app.db import get_session
from app.knowledge.models import Image
from app.uploads.api import STORAGE_DOWN, get_storage
from app.uploads.imaging import ImageRejected, process
from app.uploads.storage import Storage, StorageError

router = APIRouter(prefix="/admin/media", tags=["admin"], dependencies=[Depends(enforce)])
public_router = APIRouter(tags=["media"])
DbSession = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[Storage, Depends(get_storage)]
UPLOADED = "data/media/uploaded/"  # Image.path prefix: served by GET /media/uploaded/<name>
NAME = re.compile(r"^[0-9a-f]{40}\.jpg$")


async def _body(request: Request) -> bytes:
    limit = request.app.state.settings.upload_max_bytes
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"The picture is larger than {limit // 2**20} MB")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a picture")
    return bytes(data)


@router.post("/pictures", status_code=201, responses={413: {}, 422: {}, 503: {}})
@requires(Perm.knowledge_edit)
def upload_picture(
    request: Request,
    staff: CurrentStaff,
    session: DbSession,
    storage: StorageDep,
    data: Annotated[bytes, Depends(_body)],
    caption: Annotated[str, Query(max_length=200)] = "",
):
    """Upload a picture (JPEG, PNG, WebP or HEIC). Returns its SHA-1 and address; link it to a fault or a part in
    the editor (that edit goes into the draft like any other)."""
    settings = request.app.state.settings
    incoming = f"incoming/admin-{uuid.uuid4()}"
    try:
        storage.put(incoming, data, "application/octet-stream")
        try:
            clean = process(storage.get(incoming), settings.upload_max_bytes, settings.upload_max_px)
        except ImageRejected as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        finally:
            storage.delete([incoming])
        sha1 = hashlib.sha1(clean.data).hexdigest()
        image = session.scalar(select(Image).where(Image.sha1 == sha1))
        if image is None:
            storage.put(f"media/uploaded/{sha1}.jpg", clean.data, "image/jpeg")
            image = Image(
                sha1=sha1,
                path=f"{UPLOADED}{sha1}.jpg",
                width=clean.width,
                height=clean.height,
                caption=caption.strip() or None,
                image_type="photo (uploaded)",
            )
            session.add(image)
            session.flush()
    except StorageError as e:
        session.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, STORAGE_DOWN) from e
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="media.upload",
        entity_type="image",
        entity_id=sha1,
        before=None,
        after={"caption": image.caption, "width": clean.width, "height": clean.height, "bytes": len(clean.data)},
        ip=staff.ip,
    )
    session.commit()
    return {
        "sha1": sha1,
        "url": "/media/uploaded/" + f"{sha1}.jpg",
        "caption": image.caption,
        "width": clean.width,
        "height": clean.height,
    }


@public_router.get("/media/uploaded/{name}", include_in_schema=False, responses={404: {}, 503: {}})
def uploaded_picture(name: str, request: Request, session: DbSession, storage: StorageDep):
    """An uploaded picture: a short-lived link to the private bucket (only pictures the admin app stored)."""
    if not NAME.match(name) or session.scalar(select(Image.id).where(Image.path == UPLOADED + name)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    ttl = request.app.state.settings.upload_view_ttl_seconds
    try:
        url = storage.presign_view(f"media/uploaded/{name}", ttl)
    except StorageError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, STORAGE_DOWN) from e
    return RedirectResponse(url, status_code=307, headers={"Cache-Control": f"private, max-age={max(ttl // 2, 30)}"})
