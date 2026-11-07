"""The free demo deployment's switches (docs/deploy-free-demo.md): LITE mode without torch, photo upload off,
pictures off, and the background jobs inside the API process (BACKGROUND_JOBS=api)."""

from datetime import UTC, datetime, timedelta

import pytest

from app import background
from app.config import embeddings_enabled
from app.knowledge.importer.embed import ModelError, load_embedder
from tests.test_diagnosis_api import db_connection, knowledge, make_client, seeded_connection, variant  # noqa: F401

MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@pytest.mark.parametrize(
    ("value", "on"), [("none", False), ("NONE", False), ("off", False), ("", False), (MINILM, True)]
)
def test_lite_mode_setting(test_settings, value, on):
    assert embeddings_enabled(test_settings.model_copy(update={"embedding_model": value})) is on


def test_lite_mode_never_loads_a_model():
    with pytest.raises(ModelError, match="LITE"):
        load_embedder("none")


def test_a_lite_api_diagnoses_without_a_model(test_settings, db_session, knowledge, variant):  # noqa: F811
    with make_client(test_settings, db_session, embedding_model="none", diagnosis_search="hybrid") as c:
        body = {"vehicle": {"variant_id": variant.id}, "category_ids": ["battery"], "text": "battry weak, no start"}
        r = c.post("/api/diagnosis/sessions", json=body)
        assert r.status_code == 201, r.text
        assert c.app.state.hybrid_searches  # the text-only search
        assert all(s is None or s._embed is None for s in c.app.state.hybrid_searches.values())


def test_photo_upload_switched_off(test_settings, db_session, knowledge, variant):  # noqa: F811
    with make_client(test_settings, db_session, photo_uploads_enabled=False) as c:
        assert c.get("/api/uploads/config").json() == {"enabled": False}
        body = {"vehicle": {"variant_id": variant.id}, "category_ids": ["battery"]}
        sid = c.post("/api/diagnosis/sessions", json=body).json()["session_id"]
        assert c.get("/api/uploads", params={"session_id": sid}).json() == []
        r = c.post("/api/uploads", json={"session_id": sid, "content_type": "image/jpeg", "size": 1000})
        assert r.status_code == 503 and "switched off" in r.json()["detail"]
    with make_client(test_settings, db_session) as c:
        assert c.get("/api/uploads/config").json() == {"enabled": True}


def test_pictures_switched_off(test_settings, db_session, knowledge, variant, monkeypatch):  # noqa: F811
    from app import config

    monkeypatch.setattr(config, "get_settings", lambda: test_settings.model_copy(update={"show_pictures": False}))
    from app.diagnosis import service
    from app.parts import service as parts_service

    monkeypatch.setattr(service, "get_settings", config.get_settings)
    monkeypatch.setattr(parts_service, "get_settings", config.get_settings)
    with make_client(test_settings, db_session) as c:
        body = {"vehicle": {"variant_id": variant.id}, "category_ids": ["battery"], "text": "car makes a click sound"}
        sid = c.post("/api/diagnosis/sessions", json=body).json()["session_id"]
        ranked = c.get(f"/api/diagnosis/sessions/{sid}/result").json()["ranked"]
        assert ranked and all(f["media"] == [] for f in ranked)


# ---------------------------------------------------------------- BACKGROUND_JOBS=api


class NowExecutor:
    def submit(self, fn, *args):
        fn(*args)


def test_in_process_queue_sends_now_and_leaves_later_ones_to_the_sweep(db_connection, monkeypatch):  # noqa: F811
    sent = []
    monkeypatch.setattr(background.notify, "send", lambda session, channels, settings, nid: sent.append(nid))
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db_connection, join_transaction_mode="create_savepoint")
    q = background.InProcessQueue(factory, {}, NowExecutor())
    later = datetime.now(UTC) + timedelta(minutes=5)
    q.enqueue([("send_notification", 1, "notify-1-0", None), ("send_notification", 2, "notify-2-0", later)])
    assert sent == [1]  # 2 is deferred: the sweep sends it when due


def test_ticks_take_an_advisory_lock(db_connection, monkeypatch):  # noqa: F811
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db_connection, join_transaction_mode="create_savepoint")
    monkeypatch.setattr(background.notify, "due", lambda session: [])
    monkeypatch.setattr(background.notify_inbound, "pending", lambda session: [])
    assert background.sweep(factory) == "0 notifications, 0 webhook messages queued"
    monkeypatch.setattr(background, "_locked", lambda session, key: False)
    assert background.sweep(factory) == "another process is sweeping"
    assert background.dispatch_tick(factory) == "another process is dispatching"
    assert background.retention_tick(factory) == "another process is applying retention"


def test_the_api_starts_the_runner_only_with_background_jobs_api(test_settings, db_session, monkeypatch):
    started = []

    class Fake:
        def __init__(self, settings, factory):
            started.append(settings.background_jobs)

        def start(self):
            started.append("start")

        def stop(self):
            started.append("stop")

    monkeypatch.setattr(background, "BackgroundRunner", Fake)
    with make_client(test_settings, db_session):
        pass
    assert started == []
    with make_client(test_settings, db_session, background_jobs="api"):
        assert started == ["api", "start"]
    assert started[-1] == "stop"


def test_the_demo_needs_real_secrets_but_may_print_codes(test_settings):
    """ENVIRONMENT=demo: placeholder secrets are refused as in production; the console SMS sender is allowed."""
    from app.main import create_app
    from app.notify.sms import ConsoleSms, make_sms

    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        create_app(test_settings.model_copy(update={"environment": "demo", "auth_secret": "dev-only-change-me"}))
    with pytest.raises(RuntimeError, match="STAFF_TOTP_KEY"):
        create_app(
            test_settings.model_copy(update={"environment": "demo", "auth_secret": "x" * 64, "staff_totp_key": ""})
        )
    assert isinstance(make_sms(test_settings.model_copy(update={"environment": "demo"})), ConsoleSms)


def test_the_console_login_code_line_shows_only_the_last_4_digits(capsys):
    """The demo's logs are on Render: the login code is there, the phone number only as its last 4 digits."""
    from app.notify.sms import ConsoleSms

    sms = ConsoleSms()
    sms.send_otp("+919876500011", "482913")
    out = capsys.readouterr().out
    assert "482913" in out and "0011" in out
    assert "9876500011" not in out and "98765" not in out
    assert sms.sent == [("+919876500011", "482913")]  # tests still read the full number
