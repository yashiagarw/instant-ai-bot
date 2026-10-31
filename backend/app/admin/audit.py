"""The one way to write audit_log. Every admin write calls record(); before / after are masked first, so the log
never holds passwords, password hashes, TOTP secrets or codes, OTPs, tokens or full phone numbers."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.admin.models import AuditLog

SECRET_KEY = re.compile(r"password|secret|token|otp|totp|code_hash|api_key|auth_key", re.I)
PHONE_KEY = re.compile(r"phone|mobile", re.I)
# An Indian mobile anywhere in a string: +91 98765 43210, 919876543210, 09876543210, 9876543210.
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?([6-9]\d{4})[\s-]?(\d{5})(?!\d)")
MASK = "***"


def mask_phone(text: str) -> str:
    return PHONE.sub(lambda m: f"******{m.group(2)[-4:]}", text)


def mask(value: Any, key: str = "") -> Any:
    """A copy safe to keep: secrets replaced by ***, phone numbers cut to their last 4 digits."""
    if key and SECRET_KEY.search(key):
        return MASK if value not in (None, "") else value
    if isinstance(value, dict):
        return {str(k): mask(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [mask(v, key) for v in value]
    if isinstance(value, str):
        return mask_phone(value)
    if isinstance(value, int | float | bool) or value is None:
        if key and PHONE_KEY.search(key) and value is not None:
            return mask_phone(str(value))
        return value
    return mask_phone(str(value))  # dates, UUIDs, enums


def record(
    session: Session,
    *,
    actor_id: uuid.UUID | None,
    actor_label: str,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
) -> AuditLog:
    row = AuditLog(
        actor_id=actor_id,
        actor_label=mask_phone(actor_label),
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        before=mask(before) if before is not None else None,
        after=mask(after) if after is not None else None,
        ip=ip if ip and _is_ip(ip) else None,
    )
    session.add(row)
    session.flush()
    return row


def _is_ip(text: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False
