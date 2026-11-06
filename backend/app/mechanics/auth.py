"""Mechanic sign-in to the app (/m): a code by SMS to the phone number of their mechanic record (the same code machinery
as customer login, app/accounts/service.py), then a session cookie of their own. Only active, verified mechanics
(mechanics.verified_at, set by a super admin) can sign in; taking either away ends their sessions at the next
request. The answer to "send me a code" is the same whether or not the number belongs to a mechanic."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounts import service as accounts
from app.config import Settings
from app.mechanics.models import Mechanic, MechanicSession
from app.notify.sms import SmsSender, mask_phone

log = logging.getLogger(__name__)
COOKIE = "im_mech"
COOKIE_PATH = "/api/mechanic"


class MechanicAuthError(ValueError):
    pass


def _eligible(session: Session, phone: str) -> Mechanic | None:
    rows = session.scalars(
        select(Mechanic).where(Mechanic.phone == phone, Mechanic.active.is_(True), Mechanic.verified_at.is_not(None))
    ).all()
    if len(rows) > 1:  # two records with one number: support must fix it first
        log.warning("Mechanic sign-in refused for %s: %s mechanic records share it", mask_phone(phone), len(rows))
        return None
    return rows[0] if rows else None


def request_code(session: Session, settings: Settings, sms: SmsSender, raw_phone: str) -> str:
    """Send a code if the number belongs to an active, verified mechanic. Returns the masked number either way.
    Raises accounts.AuthError (bad number) or accounts.TooMany."""
    phone = accounts.normalize_phone(raw_phone)
    mech = _eligible(session, phone)
    if mech is None:
        log.info("Mechanic code asked for %s: not an active, verified mechanic (no code sent)", mask_phone(phone))
        return mask_phone(phone)
    code, _ = accounts.request_otp(session, settings, phone)
    sms.send_otp(phone, code)
    return mask_phone(phone)


def verify(session: Session, settings: Settings, raw_phone: str, code: str) -> tuple[Mechanic, str]:
    phone = accounts.normalize_phone(raw_phone)
    accounts.verify_otp(session, settings, phone, code)
    mech = _eligible(session, phone)
    if mech is None:
        raise MechanicAuthError("This number is not an active, verified mechanic. Please call support.")
    return mech, start_session(session, settings, mech)


def start_session(session: Session, settings: Settings, mech: Mechanic) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        MechanicSession(
            mechanic_id=mech.id,
            token_hash=accounts.token_hash(token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.mechanic_session_days),
        )
    )
    session.flush()
    return token


def current(session: Session, token: str | None) -> Mechanic | None:
    if not token:
        return None
    row = session.scalar(select(MechanicSession).where(MechanicSession.token_hash == accounts.token_hash(token)))
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    mech = session.get(Mechanic, row.mechanic_id)
    if mech is None or not mech.active or mech.verified_at is None:
        return None
    if row.last_seen_at is None or (now - row.last_seen_at).total_seconds() > 300:
        row.last_seen_at = now
    return mech


def logout(session: Session, token: str | None) -> None:
    if token:
        session.execute(
            update(MechanicSession)
            .where(MechanicSession.token_hash == accounts.token_hash(token))
            .values(revoked_at=datetime.now(UTC))
        )
