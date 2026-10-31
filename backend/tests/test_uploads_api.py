"""Photo upload API with in-memory storage: the flow, wrong types, oversize files, metadata removal and access control
(another browser, another account, not logged in)."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.db import get_session
from app.main import create_app
from app.notify.sms import ConsoleSms
from app.uploads.models import Upload
from app.uploads.storage import MemoryStorage
from tests.test_accounts import CONSENT
from tests.test_diagnosis_api import db_connection, knowledge, seeded_connection, variant  # noqa: F401
from tests.test_uploads_imaging import camera_exif, photo


@pytest.fixture
def app(test_settings, db_session, knowledge):  # noqa: F811
    app = create_app(test_settings.model_copy(update={"upload_max_bytes": 2 * 1024 * 1024}))
    app.dependency_overrides[get_session] = lambda: db_session
    app.state.storage = MemoryStorage()
    app.state.sms_sender = ConsoleSms()
    return app


def browser(app) -> TestClient:
    return TestClient(app, base_url="https://testserver")


def new_session(client, variant_id) -> str:
    r = client.post(
        "/api/diagnosis/sessions", json={"vehicle": {"variant_id": variant_id}, "category_ids": ["battery"]}
    )
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def send(app, client, sid, data: bytes, declared="image/jpeg"):
    """What the browser does: ask for a form, post the file to the storage, then ask the API to check it."""
    r = client.post("/api/uploads", json={"session_id": sid, "content_type": declared, "size": len(data)})
    assert r.status_code == 201, r.text
    form = r.json()
    app.state.storage.put(form["fields"]["key"], data, declared)
    return form, client.post(f"/api/uploads/{form['upload_id']}/complete")


def login(app, client, phone):
    client.post("/api/auth/otp/request", json={"phone": phone})
    code = app.state.sms_sender.sent[-1][1]
    assert client.post("/api/auth/otp/verify", json={"phone": phone, "code": code, **CONSENT}).status_code == 200


def test_upload_flow_stores_a_clean_private_jpeg_and_serves_signed_links(app, db_session, variant):  # noqa: F811
    c = browser(app)
    sid = new_session(c, variant.id)
    src = photo("JPEG", size=(3000, 2000), exif=camera_exif())
    form, done = send(app, c, sid, src)
    assert form["fields"]["key"] == f"incoming/{form['upload_id']}" and form["max_bytes"] == 2 * 1024 * 1024
    assert done.status_code == 200, done.text
    body = done.json()
    assert (body["status"], body["width"], body["height"]) == ("ready", 2000, 1333)
    assert body["url"].startswith("https://storage.test/photos/") and body["expires_in"] == 300
    assert done.headers["cache-control"] == "no-store"

    storage = app.state.storage
    assert f"incoming/{form['upload_id']}" not in storage.objects  # the raw upload is gone
    stored, content_type = storage.objects[f"photos/{form['upload_id']}.jpg"]
    assert content_type == "image/jpeg" and b"SecretCam" not in stored and b"Exif" not in stored
    assert Image.open(io.BytesIO(stored)).getexif().get_ifd(0x8825) == {}  # no GPS

    row = db_session.get(Upload, form["upload_id"])
    assert (row.detected_type, str(row.session_id), row.user_id) == ("jpeg", sid, None) and row.anon_key_hash
    assert c.get(f"/api/uploads/{form['upload_id']}").json()["url"]
    assert [p["id"] for p in c.get("/api/uploads", params={"session_id": sid}).json()] == [form["upload_id"]]


@pytest.mark.parametrize(
    ("data", "declared"),
    [
        (photo("GIF"), "image/jpeg"),  # a GIF claiming to be a JPEG
        (b"%PDF-1.7\n" + b"x" * 500, "image/png"),
        (b"<script>alert(1)</script>", "image/webp"),
    ],
)
def test_wrong_real_types_are_rejected_and_nothing_is_kept(app, db_session, variant, data, declared):  # noqa: F811
    c = browser(app)
    sid = new_session(c, variant.id)
    form, done = send(app, c, sid, data, declared)
    assert done.status_code == 422 and "JPEG, PNG, WebP or HEIC" in done.json()["detail"]
    assert app.state.storage.objects == {}
    row = db_session.get(Upload, form["upload_id"])
    assert (row.status, row.reject_reason) == ("rejected", "wrong_type")
    assert c.get(f"/api/uploads/{form['upload_id']}").json()["url"] is None


def test_declared_type_and_size_are_checked_before_any_upload(app, variant):  # noqa: F811
    c = browser(app)
    sid = new_session(c, variant.id)
    for body in (
        {"content_type": "application/pdf", "size": 100},
        {"content_type": "image/jpeg", "size": 3 * 1024 * 1024},
    ):
        assert c.post("/api/uploads", json={"session_id": sid, **body}).status_code == 422


def test_oversize_files_that_reach_the_storage_are_rejected(app, db_session, variant):  # noqa: F811
    c = browser(app)
    sid = new_session(c, variant.id)
    big = b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024 + 10)  # declared small, sent big
    r = c.post("/api/uploads", json={"session_id": sid, "content_type": "image/jpeg", "size": 1000})
    form = r.json()
    app.state.storage.put(form["fields"]["key"], big, "image/jpeg")
    done = c.post(f"/api/uploads/{form['upload_id']}/complete")
    assert done.status_code == 422 and "under 10 MB" in done.json()["detail"]
    assert db_session.get(Upload, form["upload_id"]).reject_reason == "too_large"
    assert app.state.storage.objects == {}


def test_complete_needs_the_file_and_runs_once(app, variant):  # noqa: F811
    c = browser(app)
    sid = new_session(c, variant.id)
    form = c.post("/api/uploads", json={"session_id": sid, "content_type": "image/png", "size": 100}).json()
    assert c.post(f"/api/uploads/{form['upload_id']}/complete").status_code == 409  # nothing uploaded yet
    app.state.storage.put(form["fields"]["key"], photo("PNG"), "image/png")
    assert c.post(f"/api/uploads/{form['upload_id']}/complete").status_code == 200
    assert c.post(f"/api/uploads/{form['upload_id']}/complete").status_code == 409


def test_at_most_n_photos_per_session(app, variant):  # noqa: F811
    c = browser(app)
    sid = new_session(c, variant.id)
    for _ in range(5):
        send(app, c, sid, photo("JPEG", size=(100, 100)))
    r = c.post("/api/uploads", json={"session_id": sid, "content_type": "image/jpeg", "size": 100})
    assert r.status_code == 409 and "up to 5 photos" in r.json()["detail"]


def test_only_the_owner_can_add_see_or_delete_photos(app, variant):  # noqa: F811
    owner = browser(app)
    sid = new_session(owner, variant.id)
    form, done = send(app, owner, sid, photo("JPEG"))
    uid = form["upload_id"]

    stranger = browser(app)  # another browser, no cookies
    new_session(stranger, variant.id)  # it has its own anonymous cookie, which is not the owner's
    for client in (stranger, browser(app)):
        assert (
            client.post("/api/uploads", json={"session_id": sid, "content_type": "image/jpeg", "size": 9}).status_code
            == 404
        )
        assert client.get(f"/api/uploads/{uid}").status_code == 404
        assert client.post(f"/api/uploads/{uid}/complete").status_code == 404
        assert client.delete(f"/api/uploads/{uid}").status_code == 404
        assert client.get("/api/uploads", params={"session_id": sid}).status_code == 404

    login(app, stranger, "9123456780")  # a logged-in customer who is not the owner
    assert stranger.get(f"/api/uploads/{uid}").status_code == 404

    login(app, owner, "9876543210")  # the owner logs in: the photo follows into the account
    assert owner.get(f"/api/uploads/{uid}").status_code == 200
    assert owner.delete(f"/api/uploads/{uid}").status_code == 204
    assert app.state.storage.objects == {} and owner.get(f"/api/uploads/{uid}").status_code == 404


def test_a_storage_outage_never_blocks_the_diagnosis(app, knowledge, variant):  # noqa: F811
    """Presigned forms are signed locally (no storage call); an outage shows when the photo is checked: 503, and
    the questions carry on."""
    c = browser(app)
    sid = new_session(c, variant.id)
    form = c.post("/api/uploads", json={"session_id": sid, "content_type": "image/jpeg", "size": 100}).json()
    app.state.storage.fail = True
    r = c.post(f"/api/uploads/{form['upload_id']}/complete")
    assert r.status_code == 503 and "carry on without a photo" in r.json()["detail"]
    main = knowledge["main"]
    opt = next(o.id for o in main.options if not o.is_not_sure)
    answer = c.post(f"/api/diagnosis/sessions/{sid}/answers", json={"question_id": main.id, "option_id": opt})
    assert answer.status_code == 200


def test_photos_need_an_owned_session_even_when_logged_in(app, db_session, variant):  # noqa: F811
    from app.diagnosis.models import DiagnosisSession

    c = browser(app)
    login(app, c, "9876543210")
    legacy = DiagnosisSession(vehicle_snapshot={}, engine_version="1.4.0")  # made before accounts: no owner
    db_session.add(legacy)
    db_session.flush()
    r = c.post("/api/uploads", json={"session_id": str(legacy.id), "content_type": "image/jpeg", "size": 100})
    assert r.status_code == 404
    assert db_session.scalar(select(Upload)) is None
