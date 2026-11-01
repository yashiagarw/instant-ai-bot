"""Dataset publish pipeline (app.datasets): the full lifecycle through the admin API with the job queue run inline:
first publish, upload a category file, validation report and diff, eval, a blocked publish, a super_admin override,
nothing lost after publish (questions, merges, requirements, phrases, safety triggers, parts, photo labels,
embeddings), embeddings only for changed text, a stale draft, discard, rollback and the worker's job handling."""

import dataclasses
from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.models import AuditLog
from app.admin.permissions import Perm
from app.datasets import jobs
from app.datasets import pipeline as P
from app.datasets.checks import artefacts
from app.datasets.evaluation import gate
from app.datasets.steps import StepInputs
from app.knowledge.importer.config import load_config
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.importer.run import run_import
from app.knowledge.models import (
    DatasetJob,
    DatasetOrigin,
    DatasetVersion,
    Embedding,
    Fault,
    FaultLink,
    JobKind,
    JobStatus,
    LinkRelation,
    Question,
    SafetyRule,
)
from app.knowledge.questions.inputs import target_version
from app.vision.models import ImageLabel
from tests.importer_fixtures import fault, make_workbook
from tests.test_admin import app, browser, code, make_staff  # noqa: F401 (app is a fixture)
from tests.test_importer import SAFETY_HEADERS

BATTERY = "BATTERY ISSUE"
PHRASES = '1. "car makes a click sound"\n2. "gaadi start nahi ho rahi"\n3. "battery down hai"\n4. "self nahi chal raha"'


def battery_rows(extra: list[dict] | None = None, drop: str | None = None, rename: str | None = None) -> list[dict]:
    rows = [
        fault("BT-01", BATTERY, rename or "Weak battery", customer_phrases=PHRASES),
        fault("BT-02", BATTERY, "Loose terminal", customer_phrases='1. "lights flicker"\n2. "terminal loose hai"'),
        fault("BT-03", BATTERY, "Swollen battery", customer_phrases='1. "battery case is swollen"\n2. "phool gayi"'),
    ]
    return [r for r in rows if r["source_id"] != drop] + (extra or [])


def battery_file(path: Path, **kw) -> Path:
    return make_workbook(
        path,
        4,
        battery_rows(**kw),
        extras={
            "SAFETY_AND_TOWING_RULES": (
                SAFETY_HEADERS,
                [
                    ["BT-03", "Swollen battery", "HIGH", "Stop, do not charge it", "No - None", "YES"],
                    ["EMERGENCY - BATTERY FIRE OR SMOKE: switch off, move away, call 112."],
                ],
            )
        },
    )


class CountingEmbedder(FakeEmbedder):
    """FakeEmbedder that remembers every text it was asked to embed."""

    def __init__(self):
        self.texts: list[str] = []

    def encode(self, texts: list[str]) -> list[list[float]]:
        self.texts += texts
        return super().encode(texts)


@pytest.fixture
def world(tmp_path, db_session):
    """Files 7 (self start + stuck) and 8 (battery), reviewed step files, an import published as the first
    version, and a pipeline that writes nothing outside tmp_path."""
    raw = tmp_path / "raw"
    raw.mkdir()
    f8 = battery_file(raw / "battery.xlsx")
    f7 = make_workbook(
        raw / "self_stuck.xlsx",
        3,
        [
            fault("SS-01", "SELF MOTOR / SELF START", "Self not taking"),
            fault("SS-02", "SELF MOTOR / SELF START", "Self slow"),
            fault("ST-01", "CAR NOT MOVING / STUCK", "Car stuck in gear"),
        ],
    )
    real = load_config()
    cfg = load_config()
    cfg.files = {7: dataclasses.replace(real.files[7], path=f7), 8: dataclasses.replace(real.files[8], path=f8)}
    cfg.review_dir, cfg.media_dir = tmp_path / "review", tmp_path / "media"

    review = tmp_path / "reviewed"
    (review / "questions").mkdir(parents=True)
    (review / "phrases").mkdir()
    (review / "parts").mkdir()
    (review / "team").mkdir()
    write(review / "questions" / "battery.yaml", {
        "category": "battery", "reviewed_by": "mechanic",
        "questions": [{
            "id": "battery-main", "status": "approved", "stage": 2, "text": "What problem are you facing?",
            "options": [
                {"label": "Car not starting", "effects": [
                    {"fault": "F08-BT-01", "effect": "supports", "strength": "strong"},
                    {"fault": "F08-BT-02", "effect": "supports", "strength": "moderate"}]},
                {"label": "Battery looks swollen", "effects": [
                    {"fault": "F08-BT-03", "effect": "supports", "strength": "strong"}]},
                {"label": "Not sure", "not_sure": True},
            ],
        }],
        # BT-03's sheet safety rule fires on the answer "Battery looks swollen" (as in the real AC files).
        "faults": {"F08-BT-03": {
            "status": "approved", "danger_phrases": ["battery phool gayi"],
            "safety_trigger_options": [{"question": "battery-main", "option": "Battery looks swollen"}]}},
        "safety_rules": [],
    })  # fmt: skip
    write(review / "merges.yaml", {"decided_by": "mechanic", "merge": [
        {"canonical": "F07-SS-01", "aliases": ["F07-SS-02"], "reason": "same fault"}]})  # fmt: skip
    write(review / "requirements.yaml", {"requirements": {"F07-SS-01": [{"feature": "start_stop"}]}})
    write(review / "phrases" / "battery.yaml", {"category": "battery", "reviewed_by": "mechanic", "phrases": [
        {"fault": "F08-BT-01", "status": "approved", "language": "hinglish", "text": "battery baith gayi",
         "english_gloss": "the battery died"}]})  # fmt: skip
    write(review / "image_labels.yaml", {"warning_light": [
        {"code": "battery_light", "name": "Battery light", "severity": "red", "look": "red battery",
         "faults": ["F08-BT-01"], "symptoms": "click", "reviewed": False}]})  # fmt: skip
    inputs = StepInputs(
        questions_dir=review / "questions",
        merges_path=review / "merges.yaml",
        requirements_path=review / "requirements.yaml",
        phrases_dir=review / "phrases",
        triggers_path=review / "triggers.yaml",
        parts_review_dir=review / "parts",
        parts_team_dir=review / "team",
        image_labels_path=review / "image_labels.yaml",
    )
    embedder = CountingEmbedder()
    pipe = P.Pipeline(diagnosis_engine="v2", config=cfg, inputs=inputs, work_dir=tmp_path / "work")
    pipe.embedder_factory = lambda: embedder

    # The importer CLI's first version, then its global rule's trigger phrases, then the first publish.
    first = run_import(db_session, cfg, list(cfg.files.values()), True, embedder, log=lambda _m: None).version
    ref = db_session.scalar(select(SafetyRule.source_ref).where(SafetyRule.scope == "global"))
    write(inputs.triggers_path, {"reviewed_by": "mechanic", "rules": {ref: {"phrases": ["battery fire", "aag"]}}})
    actor = P.Actor(None, "boss@im.test")
    P.publish(db_session, pipe, first, actor, lambda *_: None)
    db_session.commit()
    return {"pipe": pipe, "embedder": embedder, "first": first, "raw": raw, "tmp": tmp_path, "actor": actor}


def write(path: Path, doc: dict) -> None:
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


class InlineQueue:
    """Runs a job right away in the test's transaction (instead of Redis and the worker)."""

    def __init__(self, db_connection, pipe):
        self.factory = lambda: Session(bind=db_connection, join_transaction_mode="create_savepoint")
        self.pipe, self.ran = pipe, []

    def enqueue(self, job_id: int) -> None:
        self.ran.append(job_id)
        jobs.execute(self.factory, self.pipe, job_id)


@pytest.fixture
def staff(app, db_session, db_connection, test_settings, world, tmp_path):  # noqa: F811
    """Signed-in clients: a super admin and a content admin (who cannot override the gate)."""
    test_settings.dataset_upload_dir = tmp_path / "uploads"
    app.state.job_queue = InlineQueue(db_connection, world["pipe"])
    out = {}
    for email, role in (("boss@im.test", "super_admin"), ("content@im.test", "content_admin")):
        _, secret = make_staff(db_session, test_settings, email, [role])
        c = browser(app)
        r = c.post("/api/admin/auth/login", json={"email": email, "password": "correct horse battery staple",
                                                  "code": code(secret)})  # fmt: skip
        assert r.json()["next"] == "done"
        out[role] = c
    return out


def upload(client, path: Path, category: str = "battery", **params):
    return client.post(
        "/api/admin/datasets/uploads",
        params={"category": category, "name": path.name, **params},
        content=path.read_bytes(),
        headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )


def live(db_session) -> DatasetVersion:
    db_session.expire_all()
    return target_version(db_session)


def actions(db_session) -> list[str]:
    return list(db_session.scalars(select(AuditLog.action).order_by(AuditLog.id)))


def set_eval(db_session, version_id: int, draft_top3: float, draft_safety: float) -> None:
    """Pretend the eval ran with these numbers against a live version at 60% top-3 and 90% safety recall."""
    v = db_session.get(DatasetVersion, version_id)
    current = {"overall": {"top3": 0.6, "safety_recall": 0.9}}
    draft = {"overall": {"top3": draft_top3, "safety_recall": draft_safety}}
    v.eval = {"scope": {}, "draft": draft, "current": current, "gate": gate(draft, current)}
    db_session.commit()


# ---------------------------------------------------------------- the lifecycle


def test_first_publish_runs_every_step(db_session, world):
    v = live(db_session)
    assert v.id == world["first"].id and v.status == "published"
    assert db_session.scalar(select(func.count()).where(Question.dataset_version_id == v.id)) == 1
    assert db_session.scalar(select(ImageLabel.symptom_ids)), "photo labels seeded with symptom lines"
    rule = db_session.scalar(select(SafetyRule).where(SafetyRule.scope == "global"))
    assert rule.triggers["phrases"] == ["battery fire", "aag"]


def test_full_lifecycle_upload_diff_eval_blocked_override_publish(db_session, world, staff):
    boss, content = staff["super_admin"], staff["content_admin"]
    first = world["first"]
    changed = battery_file(
        world["raw"] / "battery-v2.xlsx",
        rename="Weak or old battery",
        drop="BT-02",
        extra=[
            fault("BT-04", BATTERY, "Battery drains overnight", customer_phrases='1. "raat bhar mein battery khatam"')
        ],
    )
    world["embedder"].texts.clear()
    r = upload(content, changed)
    assert r.status_code == 202, r.text
    vid, job = r.json()["version"]["id"], r.json()["job"]
    assert job["kind"] == "build"

    d = content.get(f"/api/admin/datasets/versions/{vid}").json()
    assert d["status"] == "validated", d["validation"]
    assert all(c["ok"] for c in d["validation"]["checks"] if c["blocking"])
    assert d["diff_counts"] == {"added": 1, "changed": 1, "removed": 1}
    changed_row = d["diff"]["changed"][0]
    assert changed_row["fault_key"] == "F08-BT-01"
    assert {"field": "name", "before": "Weak battery", "after": "Weak or old battery"} in changed_row["fields"]
    assert [x["fault_key"] for x in d["diff"]["removed"]] == ["F08-BT-02"]
    assert d["jobs"][0]["status"] == "succeeded" and d["jobs"][0]["progress"] == 100
    # Embeddings: only changed or new text went through the model; unchanged lines reused their vectors.
    embedded = set(world["embedder"].texts)
    assert "Weak or old battery. Weak or old battery description" in embedded
    assert "Clicking sound" not in embedded and "terminal loose hai" not in embedded
    counts = d["validation"]["steps"]["embeddings"]
    assert counts["reused"] > 0
    # The live version is untouched until publish.
    assert live(db_session).id == first.id

    # Publishing needs an eval first.
    r = content.post(f"/api/admin/datasets/versions/{vid}/publish", json={})
    assert r.status_code == 409 and "evaluation" in r.json()["detail"]

    r = content.post(f"/api/admin/datasets/versions/{vid}/eval", json={})
    assert r.status_code == 202, r.text
    ev = content.get(f"/api/admin/datasets/versions/{vid}").json()["eval"]
    assert ev["scope"] == {"categories": ["battery"], "split": "test", "full": False}
    assert ev["draft"]["version_id"] == vid and ev["current"]["version_id"] == first.id
    assert "gate" in ev

    # Blocked: top-3 down 5 points.
    set_eval(db_session, vid, 0.55, 0.9)
    r = content.post(f"/api/admin/datasets/versions/{vid}/publish", json={})
    assert r.status_code == 409 and "Top-3 accuracy drops 5.00 points" in r.json()["detail"]
    r = content.post(f"/api/admin/datasets/versions/{vid}/publish", json={"override_reason": "content admins cannot"})
    assert r.status_code == 403
    r = boss.post(f"/api/admin/datasets/versions/{vid}/publish", json={"override_reason": "too short"})
    assert r.status_code == 422
    assert live(db_session).id == first.id
    assert content.get(f"/api/admin/datasets/versions/{vid}").json()["publish"]["can_publish"] is False

    reason = "The drop is from two retired faults; mechanic checked the new rows."
    r = boss.post(f"/api/admin/datasets/versions/{vid}/publish", json={"override_reason": reason})
    assert r.status_code == 202, r.text
    now = live(db_session)
    assert now.id == vid and now.status == "published" and now.override_reason == reason
    assert db_session.get(DatasetVersion, first.id).status == "archived"
    assert db_session.scalar(select(func.count()).where(DatasetVersion.status == "published")) == 1
    override = db_session.scalar(select(AuditLog).where(AuditLog.action == "dataset.publish_override"))
    assert override.after == {"reason": reason} and "Top-3" in override.before["blocked_by"][0]
    assert {"dataset.upload", "dataset.eval", "dataset.publish_requested", "dataset.publish"} <= set(
        actions(db_session)
    )


def test_safety_recall_may_not_drop_at_all():
    current = {"overall": {"top3": 0.6, "safety_recall": 0.9}}
    assert gate({"overall": {"top3": 0.58, "safety_recall": 0.9}}, current)["ok"]  # 2 points: allowed
    assert gate({"overall": {"top3": 0.57, "safety_recall": 0.9}}, current)["ok"]  # exactly 3 points: allowed
    assert not gate({"overall": {"top3": 0.569, "safety_recall": 0.9}}, current)["ok"]
    blocked = gate({"overall": {"top3": 0.7, "safety_recall": 0.899}}, current)
    assert not blocked["ok"] and "Safety recall" in blocked["reasons"][0]
    assert gate({"overall": {"top3": 0.1, "safety_recall": None}}, None)["ok"]  # nothing to compare with


def test_nothing_is_lost_after_publish(db_session, world, staff):
    """Every step's output exists for the new version: questions, effects, merges, requirements, reviewed phrases,
    global trigger phrases, photo labels and embeddings; unchanged categories are identical."""
    content = staff["content_admin"]
    first = world["first"]
    before = artefacts(db_session, first)
    r = upload(content, battery_file(world["raw"] / "battery-v3.xlsx", rename="Weak battery (old)"))
    vid = r.json()["version"]["id"]
    set_eval(db_session, vid, 0.6, 0.9)
    assert content.post(f"/api/admin/datasets/versions/{vid}/publish", json={}).status_code == 202
    new = live(db_session)
    assert new.id == vid
    after = artefacts(db_session, new)
    for name in ("questions", "effects", "safety", "triggers", "drafted_phrases", "merges", "requirements",
                 "global_safety", "items", "dataset_phrases", "costs"):  # fmt: skip
        assert after[name] == before[name], name
    # The live tables point at the new version.
    keys = dict(db_session.execute(select(Fault.id, Fault.fault_key).where(Fault.dataset_version_id == new.id)).all())
    label = db_session.scalar(select(ImageLabel))
    assert label.symptom_ids and all(
        db_session.scalar(select(Fault.dataset_version_id).join_from(Fault, Fault.items).where(Fault.items.any(id=i)))
        == new.id
        for i in label.symptom_ids
    )
    merge = db_session.scalar(
        select(FaultLink).where(FaultLink.relation == LinkRelation.merged_into, FaultLink.from_fault_id.in_(list(keys)))
    )
    assert keys[merge.from_fault_id] == "F07-SS-02"
    from app.knowledge.embeddings import sources

    assert db_session.scalar(
        select(func.count()).where(Embedding.model_name == "fake", Embedding.fault_id.in_(list(keys)))
    ) == len(sources(db_session, new.id))


def test_a_draft_that_would_lose_a_safety_rule_is_not_validated(db_session, world, staff):
    content = staff["content_admin"]
    path = make_workbook(
        world["raw"] / "no-bt03-rule.xlsx",
        4,
        battery_rows(),  # same faults, but BT-03's safety row now belongs to BT-01 (the emergency row stays row 3)
        extras={
            "SAFETY_AND_TOWING_RULES": (
                SAFETY_HEADERS,
                [
                    ["BT-01", "Weak battery", "LOW", "Drive to a workshop", "Yes - jump start", "NO"],
                    ["EMERGENCY - BATTERY FIRE OR SMOKE: switch off, move away, call 112."],
                ],
            )
        },
    )
    vid = upload(content, path).json()["version"]["id"]
    d = content.get(f"/api/admin/datasets/versions/{vid}").json()
    assert d["status"] == "draft" and d["validated"] is False
    assert {(x["area"], x["fault_key"]) for x in d["validation"]["losses"]} == {
        ("safety rules", "F08-BT-03"),
        ("safety trigger phrases", "F08-BT-03"),
        ("safety trigger answers (answers that fire a safety rule)", "F08-BT-03"),
    }
    assert content.post(f"/api/admin/datasets/versions/{vid}/eval", json={}).status_code == 409


def test_a_reviewed_file_that_no_longer_matches_fails_the_build_with_its_step(db_session, world, staff):
    content = staff["content_admin"]
    path = make_workbook(world["raw"] / "no-safety.xlsx", 4, battery_rows())  # the global rule is gone
    vid = upload(content, path).json()["version"]["id"]
    d = content.get(f"/api/admin/datasets/versions/{vid}").json()
    assert d["status"] == "draft" and d["validated"] is None
    assert d["build_error"].startswith("safety_triggers apply: no global rule")
    assert d["jobs"][0]["status"] == "failed"
    assert live(db_session).id == world["first"].id


def test_stale_draft_needs_a_rebuild_and_discard_removes_a_draft(db_session, world, staff):
    content = staff["content_admin"]
    a = upload(content, battery_file(world["raw"] / "a.xlsx", rename="Weak battery A")).json()["version"]["id"]
    b = upload(content, battery_file(world["raw"] / "b.xlsx", rename="Weak battery B")).json()["version"]["id"]
    set_eval(db_session, a, 0.6, 0.9)
    assert content.post(f"/api/admin/datasets/versions/{a}/publish", json={}).status_code == 202
    d = content.get(f"/api/admin/datasets/versions/{b}").json()
    assert d["stale"] is True
    set_eval(db_session, b, 0.6, 0.9)
    r = content.post(f"/api/admin/datasets/versions/{b}/publish", json={})
    assert r.status_code == 409 and "Rebuild" in r.json()["detail"]
    assert content.post(f"/api/admin/datasets/versions/{b}/rebuild").status_code == 202
    d = content.get(f"/api/admin/datasets/versions/{b}").json()
    assert d["stale"] is False and d["base_version_id"] == a and d["eval"] == {}

    assert content.delete(f"/api/admin/datasets/versions/{b}").status_code == 204
    assert db_session.get(DatasetVersion, b) is None
    assert content.delete(f"/api/admin/datasets/versions/{a}").status_code == 409  # published: not a draft
    assert "dataset.discard" in actions(db_session)


def test_rollback_restores_one_category_and_keeps_the_others(db_session, world, staff):
    content = staff["content_admin"]
    first = world["first"]
    # Publish a battery change, then a self-start change.
    vb = upload(content, battery_file(world["raw"] / "bv2.xlsx", rename="Battery v2")).json()["version"]["id"]
    set_eval(db_session, vb, 0.6, 0.9)
    content.post(f"/api/admin/datasets/versions/{vb}/publish", json={})
    f7 = make_workbook(
        world["raw"] / "ss-v2.xlsx",
        3,
        [
            fault("SS-01", "SELF MOTOR / SELF START", "Self not taking (v2)"),
            fault("SS-02", "SELF MOTOR / SELF START", "Self slow"),
            fault("ST-01", "CAR NOT MOVING / STUCK", "Car stuck in gear"),
        ],
    )
    vs = upload(content, f7, category="self_start").json()["version"]["id"]
    assert content.get(f"/api/admin/datasets/versions/{vs}").json()["categories"] == ["self_start", "stuck"]
    set_eval(db_session, vs, 0.6, 0.9)
    assert content.post(f"/api/admin/datasets/versions/{vs}/publish", json={}).status_code == 202

    # Roll battery back to the first version (archived): self start keeps its v2 row.
    r = content.post(f"/api/admin/datasets/versions/{first.id}/rollback", json={"category": "battery"})
    assert r.status_code == 202, r.text
    job = db_session.get(DatasetJob, r.json()["id"])
    assert job.status == "succeeded", job.error
    now = live(db_session)
    assert now.origin == DatasetOrigin.rollback and now.rollback_of_id == first.id and now.base_version_id == vs
    names = dict(
        db_session.execute(select(Fault.fault_key, Fault.name).where(Fault.dataset_version_id == now.id)).all()
    )
    assert names["F08-BT-01"] == "Weak battery" and names["F07-SS-01"] == "Self not taking (v2)"
    assert db_session.scalar(select(func.count()).where(Question.dataset_version_id == now.id)) == 1
    assert "dataset.rollback" in actions(db_session)
    assert content.post(f"/api/admin/datasets/versions/{now.id}/rollback").status_code == 409  # not archived


# ---------------------------------------------------------------- API guards, queue and worker


def test_upload_checks(db_session, world, staff):
    content = staff["content_admin"]
    path = battery_file(world["raw"] / "ok.xlsx")
    assert upload(content, path, category="nope").status_code == 422
    r = content.post("/api/admin/datasets/uploads", params={"category": "battery", "name": "x.csv"}, content=b"a,b")
    assert r.status_code == 422
    big = content.post(
        "/api/admin/datasets/uploads", params={"category": "battery", "name": "x.xlsx"},
        content=b"PK\x03\x04" + b"0" * (26 * 1024 * 1024),
    )  # fmt: skip
    assert big.status_code == 413
    assert upload(content, path, category="battery", file_no=7).status_code == 422


def test_one_job_at_a_time_and_redis_down(db_session, world, staff, app):  # noqa: F811
    content = staff["content_admin"]
    jobs.create_job(db_session, JobKind.eval, world["first"].id, None, "someone")
    db_session.commit()
    r = upload(content, battery_file(world["raw"] / "busy.xlsx"))
    assert r.status_code == 409 and "Another job" in r.json()["detail"]
    db_session.execute(DatasetJob.__table__.update().values(status="failed"))
    db_session.commit()

    class Down:
        def enqueue(self, job_id):
            raise jobs.QueueUnavailable("connection refused")

    app.state.job_queue = Down()
    r = upload(content, battery_file(world["raw"] / "down.xlsx"))
    assert r.status_code == 503 and "start Redis" in r.json()["detail"]
    assert db_session.scalar(select(DatasetJob).order_by(DatasetJob.id.desc())).status == JobStatus.failed


def test_worker_marks_failures_and_stale_jobs(db_session, db_connection, world):
    factory = InlineQueue(db_connection, world["pipe"]).factory
    v = DatasetVersion(checksum="pending", origin=DatasetOrigin.upload, category_code="battery", source_file_no=8,
                       base_version_id=world["first"].id, validation={"upload": {"path": "/nowhere.xlsx"}})  # fmt: skip
    db_session.add(v)
    db_session.flush()
    job = jobs.create_job(db_session, JobKind.build, v.id, None, "someone")
    db_session.commit()
    assert jobs.execute(factory, world["pipe"], job.id) == "failed"
    db_session.expire_all()
    assert "missing" in db_session.get(DatasetJob, job.id).error
    assert "missing" in db_session.get(DatasetVersion, v.id).validation["error"]
    assert jobs.execute(factory, world["pipe"], job.id) == "failed"  # not queued: not run again

    running = jobs.create_job(db_session, JobKind.eval, v.id, None, "someone")
    running.status = JobStatus.running
    db_session.commit()
    assert jobs.fail_stale(factory) == [running.id]
    db_session.expire_all()
    assert "worker stopped" in db_session.get(DatasetJob, running.id).error


def test_cli_import_leaves_admin_drafts_alone_and_the_app_never_serves_them(db_session, world, staff):
    content = staff["content_admin"]
    vid = upload(content, battery_file(world["raw"] / "draft.xlsx", rename="Draft name")).json()["version"]["id"]
    pipe = world["pipe"]
    run_import(db_session, pipe.config, list(pipe.config.files.values()), True, None, log=lambda _m: None)
    assert db_session.get(DatasetVersion, vid) is not None
    assert live(db_session).id == world["first"].id


def test_the_api_switches_engines_without_a_restart(db_session, world, staff, app):  # noqa: F811
    from app.diagnosis import service

    content = staff["content_admin"]
    app.state.settings.diagnosis_search = "keyword"
    e1 = service.get_engine(app.state, db_session, app.state.settings)
    vid = upload(content, battery_file(world["raw"] / "eng.xlsx", rename="Engine switch")).json()["version"]["id"]
    set_eval(db_session, vid, 0.6, 0.9)
    content.post(f"/api/admin/datasets/versions/{vid}/publish", json={})
    e2 = service.get_engine(app.state, db_session, app.state.settings)
    assert e1.k.dataset_version_id == world["first"].id and e2.k.dataset_version_id == vid
    # A session that started on the old version keeps its engine.
    assert service.get_engine(app.state, db_session, app.state.settings, world["first"].id) is e1


def test_worker_settings():
    from app.datasets.worker import WorkerSettings, run_dataset_job

    assert WorkerSettings.functions == [run_dataset_job] and WorkerSettings.max_jobs == 1


def test_dataset_endpoints_by_role(app, db_session, test_settings, world):  # noqa: F811
    from app.admin.deps import ATTR, admin_routes
    from app.datasets.api import router

    assert {getattr(r.endpoint, ATTR) for r in admin_routes(router)} == {Perm.content_read, Perm.datasets_manage}
    v = world["first"].id
    calls = [
        ("GET", "/api/admin/datasets", None),
        ("GET", f"/api/admin/datasets/versions/{v}", None),
        ("GET", "/api/admin/datasets/jobs/1", None),
        ("POST", "/api/admin/datasets/uploads?category=battery", None),
        ("POST", f"/api/admin/datasets/versions/{v}/rebuild", None),
        ("POST", f"/api/admin/datasets/versions/{v}/eval", {}),
        ("POST", f"/api/admin/datasets/versions/{v}/publish", {}),
        ("POST", f"/api/admin/datasets/versions/{v}/rollback", {}),
        ("DELETE", f"/api/admin/datasets/versions/{v}", None),
        ("POST", "/api/admin/datasets/jobs/1/cancel", None),
    ]
    assert len(calls) == len(admin_routes(router))
    anonymous = browser(app)
    for method, path, body in calls:
        assert anonymous.request(method, path, json=body).status_code == 401, path
    for email, role in (("mech@im.test", "mechanic"), ("agent@im.test", "support_agent")):
        _, secret = make_staff(db_session, test_settings, email, [role])
        c = browser(app)
        c.post("/api/admin/auth/login", json={"email": email, "password": "correct horse battery staple",
                                              "code": code(secret)})  # fmt: skip
        for method, path, body in calls:
            assert c.request(method, path, json=body).status_code == 403, (role, path)


def test_an_unchanged_file_evaluates_like_for_like(db_session, world, staff):
    """Rule ids are new in every version; the eval still picks the same cases for both versions."""
    content = staff["content_admin"]
    vid = upload(content, battery_file(world["raw"] / "same.xlsx")).json()["version"]["id"]
    assert content.post(f"/api/admin/datasets/versions/{vid}/eval", json={"full": True}).status_code == 202
    ev = content.get(f"/api/admin/datasets/versions/{vid}").json()["eval"]
    assert ev["scope"]["full"] is True and ev["scope"]["categories"] is None
    assert ev["draft"]["cases"] == ev["current"]["cases"] > 0
    assert ev["draft"]["overall"] == ev["current"]["overall"]
    assert ev["gate"]["ok"] and ev["gate"]["top3_change"] in (0.0, None)
