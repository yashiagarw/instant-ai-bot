"""Against the real local S3 storage (docker compose up -d storage): presigned POST uploads, the size limit enforced
by the storage itself, a private bucket and short-lived signed links. Skipped when no storage is reachable."""

import uuid

import httpx2 as httpx
import pytest

from app.config import get_settings
from app.uploads.storage import S3Storage, StorageError


@pytest.fixture(scope="module")
def storage():
    settings = get_settings().model_copy(update={"s3_bucket": "autocare-uploads-test"})
    try:
        s = S3Storage(settings)
        s.setup()
    except Exception as e:  # no keys, or nothing listening
        pytest.skip(f"no local S3 storage ({type(e).__name__}): docker compose up -d storage")
    return s


def post_file(form: dict, data: bytes) -> httpx.Response:
    return httpx.post(form["url"], data=form["fields"], files={"file": ("photo.jpg", data, "image/jpeg")}, timeout=10)


def test_presigned_post_upload_private_bucket_and_signed_links(storage):
    key = f"incoming/{uuid.uuid4()}"
    form = storage.presign_upload(key, max_bytes=1000, ttl=60)
    r = post_file(form, b"\xff\xd8\xff" + b"x" * 500)
    assert r.status_code in (200, 201, 204), r.text
    assert storage.size(key) == 503

    unsigned = f"{storage.client.meta.endpoint_url}/{storage.bucket}/{key}"
    assert httpx.get(unsigned, timeout=10).status_code in (401, 403)  # private: no anonymous reads
    signed = storage.presign_view(key, ttl=60)
    got = httpx.get(signed, timeout=10)
    assert got.status_code == 200 and got.content.startswith(b"\xff\xd8\xff")

    storage.delete([key])
    assert storage.size(key) is None


def test_a_real_size_photo_uploads(storage):
    """Hundreds of kilobytes, not a few bytes: tiny files are stored inline by some servers and hide volume problems."""
    import os

    key = f"incoming/{uuid.uuid4()}"
    form = storage.presign_upload(key, max_bytes=10 * 1024 * 1024, ttl=60)
    data = b"\xff\xd8\xff" + os.urandom(400_000)
    r = post_file(form, data)
    assert r.status_code in (200, 201, 204), r.text
    assert storage.size(key) == len(data)
    storage.delete([key])


def test_the_storage_refuses_files_over_the_signed_size_limit(storage):
    key = f"incoming/{uuid.uuid4()}"
    form = storage.presign_upload(key, max_bytes=1000, ttl=60)
    r = post_file(form, b"\xff\xd8\xff" + b"x" * 5000)
    assert r.status_code >= 400 and storage.size(key) is None


def test_a_tampered_form_is_refused(storage):
    key = f"incoming/{uuid.uuid4()}"
    form = storage.presign_upload(key, max_bytes=1000, ttl=60)
    form["fields"]["key"] = "photos/someone-elses.jpg"  # the policy is signed for the original key
    r = post_file(form, b"\xff\xd8\xff" + b"x" * 100)
    assert r.status_code not in (200, 201, 204)  # refused (S3 answers 403; SeaweedFS redirects without storing)
    assert storage.size("photos/someone-elses.jpg") is None


def test_storage_errors_are_reported_as_storage_errors(storage):
    with pytest.raises(StorageError):
        storage.get(f"photos/{uuid.uuid4()}.jpg")
