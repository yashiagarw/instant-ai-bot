"""Staff access control: every admin endpoint with every role (allow / deny), staff login (password + TOTP, lockout,
no code reuse, short sessions), customer and staff cookies kept apart, deny by default, the audit log (every write,
masked, append-only) and the CLI that creates the first super admin."""

import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyotp
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.accounts.models import AuthSession
from app.admin import cli, service
from app.admin.audit import mask
from app.admin.deps import ATTR, STAFF_COOKIE, admin_routes, check_admin_routes, enforce, requires
from app.admin.models import STAFF_ROLES, AuditLog, RoleCode, StaffSession, StaffUser
from app.admin.permissions import PUBLIC, ROLE_PERMISSIONS, Perm
from app.db import get_session
from app.llm.models import GeneratedQuestion
from app.main import create_app
from app.notify.sms import ConsoleSms
from app.requests.models import ServiceRequest

PASSWORD = "correct horse battery staple"
DOCS = Path(__file__).resolve().parents[2] / "docs" / "permissions.md"


@pytest.fixture
def app(test_settings, db_session):
    app = create_app(test_settings)
    app.dependency_overrides[get_session] = lambda: db_session
    app.state.sms_sender = ConsoleSms()
    return app


def browser(app) -> TestClient:
    return TestClient(app, base_url="https://testserver")


def code(secret: str, ahead: int = 0) -> str:
    """The code for now (+ `ahead` 30 s steps: a later step, since a used step is refused)."""
    return pyotp.TOTP(secret).at(time.time() + 30 * ahead)


def make_staff(db_session, settings, email, roles, password=PASSWORD):
    user, secret = service.create_staff(db_session, settings, service.CLI, email, email.split("@")[0], password, roles)
    db_session.commit()
    return user, secret


def sign_in(app, email, secret, password=PASSWORD, ahead=0) -> TestClient:
    c = browser(app)
    r = c.post("/api/admin/auth/login", json={"email": email, "password": password, "code": code(secret, ahead)})
    assert r.status_code == 200, r.text
    return c


def customer(app) -> TestClient:
    c = browser(app)
    assert c.post("/api/auth/otp/request", json={"phone": "9876543210"}).status_code == 202
    otp = app.state.sms_sender.sent[-1][1]
    r = c.post("/api/auth/otp/verify", json={"phone": "9876543210", "code": otp, "consent": True,
                                             "consent_text_version": "account-v1"})  # fmt: skip
    assert r.status_code == 200, r.text
    return c


def audit_count(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(AuditLog))


# ---------------------------------------------------------------- every endpoint x every role


@pytest.fixture
def targets(db_session, test_settings):
    target, _ = make_staff(db_session, test_settings, "target@im.test", ["mechanic"])
    req = ServiceRequest(
        reference="IM-ADMIN1", name="Asha", phone="+919800001234", consent_given=True,
        consent_text_version="request-v1", consent_at=datetime.now(UTC),
    )  # fmt: skip
    q = GeneratedQuestion(text="Is the belt squealing?", options=["Yes", "No"], model="m", prompt_version="v")
    db_session.add_all([req, q])
    db_session.commit()
    return {"staff_id": target.id, "request_id": req.id, "question_id": q.id}


def calls(t: dict, who: str, secret: str) -> list[tuple[str, str, dict | None]]:
    """One call per admin endpoint with a valid body; logout last."""
    return [
        ("POST", "/api/admin/auth/login", {"email": "nobody@im.test", "password": "x", "code": "000000"}),
        ("GET", "/api/admin/auth/me", None),
        ("POST", "/api/admin/auth/password",
         {"current_password": PASSWORD, "code": code(secret, 1), "new_password": "a brand new passphrase 77"}),
        ("GET", "/api/admin/staff", None),
        ("POST", "/api/admin/staff",
         {"email": f"new-{who}@im.test", "name": "New", "password": "a long enough pass 1", "roles": ["mechanic"]}),
        ("PUT", f"/api/admin/staff/{t['staff_id']}/roles", {"roles": ["mechanic", "support_agent"]}),
        ("POST", f"/api/admin/staff/{t['staff_id']}/deactivate", None),
        ("POST", f"/api/admin/staff/{t['staff_id']}/activate", None),
        ("POST", f"/api/admin/staff/{t['staff_id']}/unlock", None),
        ("POST", f"/api/admin/staff/{t['staff_id']}/reset-two-factor", None),
        ("GET", "/api/admin/audit", None),
        ("GET", "/api/admin/requests", None),
        ("GET", f"/api/admin/requests/{t['request_id']}", None),
        ("PATCH", f"/api/admin/requests/{t['request_id']}", {"status": "contacted"}),
        ("GET", "/api/admin/content/generated-questions", None),
        ("POST", f"/api/admin/content/generated-questions/{t['question_id']}/review", {"decision": "approved"}),
        ("GET", "/api/admin/content/image-labels", None),
        ("POST", "/api/admin/auth/logout", None),
    ]  # fmt: skip


def permission_of(app, method: str, path: str) -> str:
    from app.admin import api

    for r in admin_routes(api.router):
        pattern = "^/api" + re.sub(r"\{[^}]+\}", "[^/]+", r.path) + "$"
        if method in r.methods and re.match(pattern, path):
            return getattr(r.endpoint, ATTR)
    raise AssertionError(f"no admin route for {method} {path}")


def test_the_matrix_covers_every_admin_endpoint(app, targets):
    from app.admin import api

    routes = {(sorted(r.methods)[0], "/api" + r.path) for r in admin_routes(api.router)}
    called = {(m, p) for m, p, _ in calls(targets, "x", pyotp.random_base32())}
    matched = set()
    for m, p in called:
        for rm, rp in routes:
            if m == rm and re.match("^" + re.sub(r"\{[^}]+\}", "[^/]+", rp) + "$", p):
                matched.add((rm, rp))
    assert matched == routes


@pytest.mark.parametrize("who", ["anonymous", "customer", *[r.value for r in STAFF_ROLES]])
def test_every_admin_endpoint_with_every_role(app, db_session, test_settings, targets, who):
    secret = ""
    if who == "anonymous":
        client = browser(app)
    elif who == "customer":
        client = customer(app)  # a real customer login: its cookie must not open /api/admin
    else:
        _, secret = make_staff(db_session, test_settings, f"{who}@im.test", [who])
        client = sign_in(app, f"{who}@im.test", secret)
    perms = ROLE_PERMISSIONS[RoleCode(who)] if who not in ("anonymous",) else frozenset()

    for method, path, body in calls(targets, who, secret or pyotp.random_base32()):
        perm = permission_of(app, method, path)
        before = audit_count(db_session)
        r = client.request(method, path, json=body)
        if perm == PUBLIC:
            assert r.status_code == 401 and r.json()["detail"] == service.LOGIN_FAILED, (who, path, r.text)
            continue
        if who in ("anonymous", "customer"):
            assert r.status_code == 401, (who, method, path, r.status_code)
        elif Perm(perm) in perms:
            assert r.status_code < 400, (who, method, path, r.status_code, r.text)
            if method != "GET":  # every admin write leaves an audit row
                assert audit_count(db_session) > before, (who, method, path)
        else:
            assert r.status_code == 403, (who, method, path, r.status_code)
            assert audit_count(db_session) == before


def test_permission_map_and_docs_agree():
    doc = DOCS.read_text(encoding="utf-8")
    rows = {}
    for line in doc.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0].startswith("`"):
            rows[cells[0].strip("`")] = cells[1:]
    roles = [RoleCode.super_admin, RoleCode.content_admin, RoleCode.support_agent, RoleCode.mechanic, RoleCode.customer]
    assert set(rows) == {p.value for p in Perm}
    for perm, marks in rows.items():
        for role, mark in zip(roles, marks, strict=True):
            assert (mark == "yes") == (Perm(perm) in ROLE_PERMISSIONS[role]), (perm, role, mark)


# ---------------------------------------------------------------- deny by default


def test_a_route_without_a_permission_is_refused_and_blocks_startup(app):
    router = APIRouter(prefix="/admin", dependencies=[Depends(enforce)])

    @router.get("/forgot")
    def forgot():
        return {"leak": True}

    @router.get("/fine")
    @requires(Perm.audit_read)
    def fine():
        return {}

    test_app = FastAPI()
    test_app.state.settings = app.state.settings
    test_app.include_router(router, prefix="/api")
    test_app.dependency_overrides[get_session] = app.dependency_overrides[get_session]
    assert TestClient(test_app).get("/api/admin/forgot").status_code == 403
    assert TestClient(test_app).get("/api/admin/fine").status_code == 401
    with pytest.raises(RuntimeError, match="declares no permission"):
        check_admin_routes(test_app, router)

    stray = FastAPI()
    stray.include_router(APIRouter(prefix="/admin", dependencies=[Depends(enforce)]), prefix="/api")
    other = APIRouter()

    @other.get("/api/admin/backdoor")
    def backdoor():
        return {}

    stray.include_router(other)
    with pytest.raises(RuntimeError, match="outside the admin router"):
        check_admin_routes(stray, APIRouter(prefix="/admin", dependencies=[Depends(enforce)]))


# ---------------------------------------------------------------- login


def test_login_cookie_is_separate_strict_and_short(app, db_session, test_settings):
    _, secret = make_staff(db_session, test_settings, "boss@im.test", ["super_admin"])
    c = browser(app)
    r = c.post("/api/admin/auth/login", json={"email": "Boss@IM.test ", "password": PASSWORD, "code": code(secret)})
    assert r.status_code == 200 and r.json()["roles"] == ["super_admin"]
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{STAFF_COOKIE}=") and "HttpOnly" in cookie and "Secure" in cookie
    assert "SameSite=strict" in cookie and "Path=/api/admin" in cookie and "Max-Age=28800" in cookie
    expires = datetime.fromisoformat(r.json()["session_expires_at"])
    assert timedelta(hours=7) < expires - datetime.now(UTC) <= timedelta(hours=8)  # customers: 30 days
    # The staff cookie is not a customer login, and a customer login is not a staff one.
    assert c.get("/api/me").status_code == 401
    cust = customer(app)
    assert cust.get("/api/admin/auth/me").status_code == 401
    cust.cookies.set(STAFF_COOKIE, cust.cookies.get("im_session"), domain="testserver.local", path="/api/admin")
    assert cust.get("/api/admin/auth/me").status_code == 401  # a customer token in the staff cookie: still no


def test_wrong_password_code_or_email_get_the_same_answer_and_codes_cannot_be_reused(app, db_session, test_settings):
    _, secret = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    c = browser(app)
    for body in (
        {"email": "agent@im.test", "password": "wrong password!!", "code": code(secret)},
        {"email": "agent@im.test", "password": PASSWORD, "code": "123456"},
        {"email": "ghost@im.test", "password": PASSWORD, "code": code(secret)},
    ):
        r = c.post("/api/admin/auth/login", json=body)
        assert r.status_code == 401 and r.json()["detail"] == service.LOGIN_FAILED
    used = code(secret)
    assert (
        c.post("/api/admin/auth/login", json={"email": "agent@im.test", "password": PASSWORD, "code": used}).status_code
        == 200
    )
    again = browser(app).post(
        "/api/admin/auth/login", json={"email": "agent@im.test", "password": PASSWORD, "code": used}
    )
    assert again.status_code == 401  # the same code a second time


def test_lockout_after_repeated_failures_and_unlock(app, db_session, test_settings):
    _, boss = make_staff(db_session, test_settings, "boss@im.test", ["super_admin"])
    user, secret = make_staff(db_session, test_settings, "mech@im.test", ["mechanic"])
    c = browser(app)
    for _ in range(test_settings.staff_max_failed_logins):
        c.post("/api/admin/auth/login", json={"email": "mech@im.test", "password": "nope nope nope", "code": "000000"})
    r = c.post("/api/admin/auth/login", json={"email": "mech@im.test", "password": PASSWORD, "code": code(secret)})
    assert r.status_code == 401 and "Too many failed attempts" in r.json()["detail"] and "Retry-After" in r.headers
    db_session.refresh(user)
    assert user.locked_until > datetime.now(UTC)
    actions = db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(user.id))).all()
    assert "staff.locked" in actions and "staff.login_locked" in actions

    admin = sign_in(app, "boss@im.test", boss)
    assert admin.post(f"/api/admin/staff/{user.id}/unlock").json()["locked"] is False
    sign_in(app, "mech@im.test", secret, ahead=1)


def test_sessions_end_when_idle_or_expired_and_on_deactivation(app, db_session, test_settings):
    _, boss = make_staff(db_session, test_settings, "boss@im.test", ["super_admin"])
    user, secret = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    c = sign_in(app, "agent@im.test", secret)
    row = db_session.scalar(select(StaffSession).where(StaffSession.staff_user_id == user.id))
    row.last_seen_at = datetime.now(UTC) - timedelta(minutes=test_settings.staff_idle_minutes + 1)
    db_session.commit()
    assert c.get("/api/admin/auth/me").status_code == 401

    c = sign_in(app, "agent@im.test", secret, ahead=1)
    row = db_session.scalars(
        select(StaffSession).where(StaffSession.staff_user_id == user.id).order_by(StaffSession.id.desc())
    ).first()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert c.get("/api/admin/auth/me").status_code == 401

    user.totp_last_step = None  # (test only) so the current code can sign in a third time
    db_session.commit()
    c = sign_in(app, "agent@im.test", secret)
    admin = sign_in(app, "boss@im.test", boss)
    assert admin.post(f"/api/admin/staff/{user.id}/deactivate").status_code == 200
    assert c.get("/api/admin/auth/me").status_code == 401


def test_there_is_always_one_active_super_admin(app, db_session, test_settings):
    me, secret = make_staff(db_session, test_settings, "boss@im.test", ["super_admin"])
    c = sign_in(app, "boss@im.test", secret)
    assert c.put(f"/api/admin/staff/{me.id}/roles", json={"roles": ["mechanic"]}).status_code == 422
    assert c.post(f"/api/admin/staff/{me.id}/deactivate").status_code == 422
    assert c.put(f"/api/admin/staff/{me.id}/roles", json={"roles": ["customer"]}).status_code == 422
    r = c.post("/api/admin/staff", json={"email": "x@im.test", "name": "X", "password": "short", "roles": ["mechanic"]})
    assert r.status_code == 422


def test_mechanics_see_masked_phone_numbers_support_sees_them_in_full(app, db_session, test_settings, targets):
    _, m = make_staff(db_session, test_settings, "mech@im.test", ["mechanic"])
    _, s = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    path = f"/api/admin/requests/{targets['request_id']}"
    assert sign_in(app, "mech@im.test", m).get(path).json()["phone"] == "******1234"
    assert sign_in(app, "agent@im.test", s).get(path).json()["phone"] == "+919800001234"


# ---------------------------------------------------------------- audit log


def test_audit_rows_never_hold_secrets_or_full_phone_numbers(app, db_session, test_settings, targets):
    _, boss = make_staff(db_session, test_settings, "boss@im.test", ["super_admin"])
    c = sign_in(app, "boss@im.test", boss)
    new = {"email": "new@im.test", "name": "New", "password": "a long enough pass 1", "roles": ["mechanic"]}
    created = c.post("/api/admin/staff", json=new).json()
    secret = created["two_factor"]["secret"]
    c.post(f"/api/admin/staff/{created['staff']['id']}/reset-two-factor")
    c.patch(f"/api/admin/requests/{targets['request_id']}", json={"status": "contacted"})
    c.post("/api/admin/auth/password", json={"current_password": PASSWORD, "code": code(boss, 1),
                                             "new_password": "an even better passphrase 2"})  # fmt: skip
    rows = db_session.execute(text("select before::text, after::text, actor_label from audit_log")).all()
    dump = " ".join(" ".join(x or "" for x in r) for r in rows)
    for leaked in (
        secret,
        boss,
        "a long enough pass 1",
        "an even better passphrase 2",
        PASSWORD,
        "9800001234",
        "argon2",
    ):
        assert leaked not in dump, leaked
    one = db_session.scalar(select(AuditLog).where(AuditLog.action == "request.set_status"))
    assert one.before == {"status": "submitted"} and one.after == {"status": "contacted"}
    assert one.actor_label == "boss@im.test" and str(one.ip) and one.at

    m = mask(
        {"phone": "+919876543210", "note": "call 98765 43210", "password": "p", "totp_secret": "s", "otp": "1",
         "new_password": "n", "code": "oil_pressure", "nested": [{"token_hash": "t", "mobile": 9876543210}]}
    )  # fmt: skip
    assert m == {"phone": "******3210", "note": "call ******3210", "password": "***", "totp_secret": "***",
                 "otp": "***", "new_password": "***", "code": "oil_pressure",
                 "nested": [{"token_hash": "***", "mobile": "******3210"}]}  # fmt: skip


def test_the_audit_log_is_append_only(db_session):
    from app.admin import audit

    row = audit.record(db_session, actor_id=None, actor_label="cli", action="t", entity_type="x")
    db_session.flush()
    for sql in ("update audit_log set action = 'changed' where id = :id", "delete from audit_log where id = :id"):
        with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
            db_session.execute(text(sql), {"id": row.id})


# ---------------------------------------------------------------- the first super admin (CLI)


def test_cli_creates_the_first_super_admin_after_a_confirmed_code(app, db_session, test_settings):
    printed: list[str] = []
    answers: dict = {}

    def ask(prompt):
        key = re.search(r"Key: ([A-Z2-7 ]+)", "\n".join(printed)).group(1).replace(" ", "")
        answers["secret"], answers["code"] = key, pyotp.TOTP(key).now()
        return answers["code"]

    passwords = iter([PASSWORD, PASSWORD])
    rc = cli.create_super_admin(db_session, test_settings, "Me@IM.test", "Me", ask, lambda p: next(passwords),
                                printed.append)  # fmt: skip
    assert rc == 0
    out = "\n".join(printed)
    assert "otpauth://totp/Instant%20Mechanic:me%40im.test" in out
    assert any(ch in out for ch in "█▀▄")  # a QR code drawn in the terminal
    user = service.find(db_session, "me@im.test")
    assert user.role_codes == ["super_admin"] and user.totp_secret_enc != answers["secret"]
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "staff.create")).actor_label == "cli"
    # The code just typed cannot sign in; the next one can.
    c = browser(app)
    r = c.post("/api/admin/auth/login", json={"email": "me@im.test", "password": PASSWORD,
                                              "code": answers["code"]})  # fmt: skip
    assert r.status_code == 401
    sign_in(app, "me@im.test", answers["secret"], ahead=1)
    # A second "first" super admin is refused.
    printed.clear()
    assert cli.create_super_admin(db_session, test_settings, "two@im.test", "Two", ask, lambda p: PASSWORD,
                                  printed.append) == 1  # fmt: skip
    assert "already exists" in printed[-1]


def test_cli_does_not_save_without_a_matching_code(db_session, test_settings):
    printed: list[str] = []
    rc = cli.create_super_admin(db_session, test_settings, "me@im.test", "Me", lambda p: "000000",
                                lambda p: PASSWORD, printed.append)  # fmt: skip
    assert rc == 1 and "Not saved" in printed[-1]
    assert db_session.scalar(select(func.count()).select_from(StaffUser)) == 0


def test_customer_login_still_works(app):
    c = customer(app)
    assert c.get("/api/me").json()["user"]["phone_masked"].endswith("3210")


def test_staff_tokens_and_customer_tokens_are_different_tables(app, db_session, test_settings):
    _, secret = make_staff(db_session, test_settings, "mech@im.test", ["mechanic"])
    sign_in(app, "mech@im.test", secret)
    customer(app)
    assert db_session.scalar(select(func.count()).select_from(StaffSession)) == 1
    assert db_session.scalar(select(func.count()).select_from(AuthSession)) == 1
    assert uuid.UUID(str(service.find(db_session, "mech@im.test").id))
