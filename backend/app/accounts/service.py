"""Phone + OTP login, cookie sessions, ownership of diagnosis sessions and requests, and account deletion.

- Codes: 6 random digits, stored as HMAC-SHA256(AUTH_SECRET, phone|code) (a plain hash of 6 digits is reversed in
  a moment), valid OTP_TTL_SECONDS, at most OTP_MAX_ATTEMPTS checks, one use. A new code replaces the older ones.
- Per phone: at most OTP_PHONE_LIMIT codes per window, counted in the database (by phone hash).
- Login: a random 32-byte token in an HttpOnly cookie; the table keeps its SHA-256 only.
- Anonymous visitors get an HttpOnly "anon" cookie; new sessions and requests keep its SHA-256, and logging in
  attaches the rows with that hash to the account. Nobody can claim a session just by knowing its id.
"""

import hashlib
import hmac
import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.accounts.models import AccountDeletion, AuthSession, OtpRequest, User, UserVehicle
from app.config import Settings
from app.diagnosis.models import DiagnosisSession
from app.llm.models import GeneratedQuestion
from app.requests.models import ServiceRequest
from app.vehicles.models import UnlistedVehicle

CONSENT_VERSION = "account-v1"
CONSENT_TEXT = (
    "I agree that Instant Mechanic stores my mobile number to create my account and keep my cars, diagnoses and "
    "requests in it. I can delete my account and this data at any time."
)
SESSION_COOKIE = "im_session"
ANON_COOKIE = "im_anon"
PHONE_RE = re.compile(r"^[6-9]\d{9}$")


class AuthError(ValueError):
    """Shown to the customer as it is."""


class TooMany(AuthError):
    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after


def now() -> datetime:
    return datetime.now(UTC)


def normalize_phone(raw: str) -> str:
    """Indian mobile -> +91XXXXXXXXXX. Accepts 98765 43210, 09876543210, +91-98765-43210, 919876543210."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not PHONE_RE.match(digits):
        raise AuthError("Enter a 10-digit Indian mobile number")
    return f"+91{digits}"


def _hmac(settings: Settings, *parts: str) -> str:
    return hmac.new(settings.auth_secret.encode(), "|".join(parts).encode(), hashlib.sha256).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- codes


def request_otp(session: Session, settings: Settings, phone: str, at: datetime | None = None) -> tuple[str, OtpRequest]:
    """Make a new code for the phone (the caller sends it). Raises TooMany past the per-phone limit."""
    at = at or now()
    phone_hash = _hmac(settings, "phone", phone)
    since = at - timedelta(seconds=settings.otp_phone_window_seconds)
    recent = session.scalars(
        select(OtpRequest.created_at)
        .where(OtpRequest.phone_hash == phone_hash, OtpRequest.created_at > since)
        .order_by(OtpRequest.created_at)
    ).all()
    if len(recent) >= settings.otp_phone_limit:
        wait = (recent[0] + timedelta(seconds=settings.otp_phone_window_seconds) - at).total_seconds()
        raise TooMany("Too many codes for this number. Please wait and try again.", max(1.0, wait))
    # Older codes for this phone stop working: only the newest one counts.
    session.execute(
        update(OtpRequest)
        .where(OtpRequest.phone_hash == phone_hash, OtpRequest.consumed_at.is_(None))
        .values(consumed_at=at)
    )
    code = f"{secrets.randbelow(10**6):06d}"
    otp = OtpRequest(
        phone_hash=phone_hash,
        code_hash=_hmac(settings, "code", phone, code),
        expires_at=at + timedelta(seconds=settings.otp_ttl_seconds),
        created_at=at,
    )
    session.add(otp)
    session.flush()
    return code, otp


def verify_otp(session: Session, settings: Settings, phone: str, code: str, at: datetime | None = None) -> None:
    """Check the newest code for the phone; raises AuthError when it is wrong, expired, used up or missing."""
    at = at or now()
    otp = session.scalar(
        select(OtpRequest)
        .where(OtpRequest.phone_hash == _hmac(settings, "phone", phone), OtpRequest.consumed_at.is_(None))
        .order_by(OtpRequest.created_at.desc())
        .with_for_update()
    )
    if otp is None:
        raise AuthError("Ask for a new code")
    if otp.expires_at <= at:
        otp.consumed_at = at
        raise AuthError("This code has expired. Ask for a new one.")
    if otp.attempts >= settings.otp_max_attempts:
        otp.consumed_at = at
        raise AuthError("Too many wrong tries. Ask for a new code.")
    otp.attempts += 1
    if not re.fullmatch(r"\d{6}", code or "") or not hmac.compare_digest(
        otp.code_hash, _hmac(settings, "code", phone, code)
    ):
        left = settings.otp_max_attempts - otp.attempts
        if left <= 0:
            otp.consumed_at = at
            raise AuthError("Too many wrong tries. Ask for a new code.")
        raise AuthError(f"That code is not right. {left} {'try' if left == 1 else 'tries'} left.")
    otp.consumed_at = at


# ---------------------------------------------------------------- logins


def login(session: Session, settings: Settings, phone: str, anon_token: str | None) -> tuple[User, str, dict]:
    """The user for the phone (created on first login, with the consent record), a new login token, and what was
    attached. The caller has checked that the customer ticked the current consent wording."""
    user = session.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone, consent_text_version=CONSENT_VERSION, consent_at=now())
        session.add(user)
        session.flush()
    user.consent_text_version, user.consent_at = CONSENT_VERSION, now()
    user.last_login_at = now()
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=now() + timedelta(days=settings.auth_session_days),
        )
    )
    attached = attach_anonymous(session, user, anon_token)
    session.flush()
    return user, token, attached


def current_user(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    auth = session.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now(),
        )
    )
    return session.get(User, auth.user_id) if auth else None


def logout(session: Session, token: str | None) -> None:
    if token:
        session.execute(update(AuthSession).where(AuthSession.token_hash == token_hash(token)).values(revoked_at=now()))


# ---------------------------------------------------------------- ownership


def save_vehicle(session: Session, user: User, ds: DiagnosisSession) -> None:
    """Keep a catalogue car the customer diagnosed in "My garage" (once per variant)."""
    if ds.variant_id is None:
        return
    exists = session.scalar(
        select(UserVehicle.id).where(UserVehicle.user_id == user.id, UserVehicle.variant_id == ds.variant_id)
    )
    if exists is None:
        snap = ds.vehicle_snapshot or {}
        label = " ".join(str(x) for x in (snap.get("make"), snap.get("model")) if x)
        label += f" · {snap['variant']}" if snap.get("variant") else ""
        session.add(UserVehicle(user_id=user.id, variant_id=ds.variant_id, label=label, snapshot=snap))
        session.flush()


def claim(session: Session, row: DiagnosisSession | ServiceRequest, user: User | None, anon_token: str) -> None:
    """Mark a new session or request as the user's, or as this browser's (anonymous cookie)."""
    if user is not None:
        row.user_id = user.id
        if isinstance(row, DiagnosisSession):
            save_vehicle(session, user, row)
    else:
        row.anon_key_hash = token_hash(anon_token)
    session.flush()


def attach_anonymous(session: Session, user: User, anon_token: str | None) -> dict:
    if not anon_token:
        return {"sessions": 0, "requests": 0}
    h = token_hash(anon_token)
    sessions = session.scalars(
        select(DiagnosisSession).where(DiagnosisSession.anon_key_hash == h, DiagnosisSession.user_id.is_(None))
    ).all()
    for ds in sessions:
        ds.user_id, ds.anon_key_hash = user.id, None
        save_vehicle(session, user, ds)
    n_requests = session.execute(
        update(ServiceRequest)
        .where(ServiceRequest.anon_key_hash == h, ServiceRequest.user_id.is_(None))
        .values(user_id=user.id, anon_key_hash=None)
    ).rowcount
    return {"sessions": len(sessions), "requests": n_requests}


# ---------------------------------------------------------------- account deletion


@dataclass
class DeletionReport:
    sessions: int
    requests: int
    vehicles: int
    uploads: bool


def delete_account(session: Session, settings: Settings, user: User) -> DeletionReport:
    """Delete the user and everything personal linked to them (DPDP Act): logins, codes, saved cars, diagnosis
    sessions with their answers, typed messages and results, typed-in unlisted cars, service requests with their
    contact details and consent records, and the user's uploads folder. A count-only receipt is kept."""
    ids = list(session.scalars(select(DiagnosisSession.id).where(DiagnosisSession.user_id == user.id)))
    unlisted = [
        u
        for u in session.scalars(
            select(DiagnosisSession.unlisted_vehicle_id).where(
                DiagnosisSession.id.in_(ids), DiagnosisSession.unlisted_vehicle_id.is_not(None)
            )
        )
    ]
    vehicles = session.scalar(select(func.count()).select_from(UserVehicle).where(UserVehicle.user_id == user.id))
    requests = session.execute(delete(ServiceRequest).where(ServiceRequest.user_id == user.id)).rowcount
    if ids:
        session.execute(delete(GeneratedQuestion).where(GeneratedQuestion.session_id.in_(ids)))
        session.execute(
            delete(DiagnosisSession).where(DiagnosisSession.id.in_(ids))
        )  # events, results, feedback cascade
    if unlisted:
        session.execute(delete(UnlistedVehicle).where(UnlistedVehicle.id.in_(unlisted)))
    session.execute(delete(OtpRequest).where(OtpRequest.phone_hash == _hmac(settings, "phone", user.phone)))
    folder = Path(settings.uploads_dir) / str(user.id)
    uploads = folder.is_dir()
    if uploads:
        shutil.rmtree(folder)
    session.delete(user)  # auth sessions and saved cars cascade
    report = DeletionReport(sessions=len(ids), requests=requests, vehicles=vehicles or 0, uploads=uploads)
    session.add(AccountDeletion(counts=report.__dict__))
    session.flush()
    return report


def new_anon_token() -> str:
    return secrets.token_urlsafe(32)
