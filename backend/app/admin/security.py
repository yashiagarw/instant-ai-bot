"""Passwords (argon2id), TOTP (RFC 6238, 30 s steps, one step of clock drift, no reuse) and TOTP secret encryption."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings

HASHER = PasswordHasher()  # argon2id with the library's current recommended parameters
# Verified against when the email is unknown, so a wrong email takes as long as a wrong password.
DUMMY_HASH = HASHER.hash("not-a-real-password-just-for-timing")
MIN_PASSWORD = 12
PLACEHOLDERS = {"", "change-me"}


class WeakPassword(ValueError):
    pass


def hash_password(password: str) -> str:
    return HASHER.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return HASHER.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    return HASHER.check_needs_rehash(stored)


def check_password_policy(password: str, email: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise WeakPassword(f"Use at least {MIN_PASSWORD} characters")
    if len(set(password)) < 6:
        raise WeakPassword("Use a less repetitive password")
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in password.lower():
        raise WeakPassword("Don't use your email name in the password")


def temporary_password() -> str:
    """For an invitation: 16 random URL-safe characters, shown once; the person changes it after signing in."""
    while True:
        pw = secrets.token_urlsafe(12)
        if len(set(pw)) >= 8:
            return pw


def fernet(settings: Settings) -> Fernet:
    key = settings.staff_totp_key
    if key in PLACEHOLDERS:
        if settings.environment in ("production", "demo"):  # demo: the public free demo
            raise RuntimeError(f"Set STAFF_TOTP_KEY (a Fernet key) in {settings.environment}")
        key = base64.urlsafe_b64encode(hashlib.sha256(f"staff-totp|{settings.auth_secret}".encode()).digest()).decode()
    try:
        return Fernet(key)
    except ValueError as e:
        raise RuntimeError("STAFF_TOTP_KEY is not a valid Fernet key (see .env.example)") from e


def new_totp_secret() -> str:
    return pyotp.random_base32()  # 160 bits


def encrypt_secret(settings: Settings, secret: str) -> str:
    return fernet(settings).encrypt(secret.encode()).decode()


def decrypt_secret(settings: Settings, token: str) -> str | None:
    try:
        return fernet(settings).decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def provisioning_uri(settings: Settings, secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.staff_totp_issuer)


def totp_step(secret: str, code: str, last_step: int | None, at: float | None = None) -> int | None:
    """The time step the code is valid for (now, or one step either side), or None. A step at or before
    `last_step` was already used: refused, so a seen code cannot be replayed."""
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    now = at if at is not None else time.time()
    step = int(now // totp.interval)
    for s in (step, step - 1, step + 1):
        if pyotp.utils.strings_equal(totp.generate_otp(s), code) and (last_step is None or s > last_step):
            return s
    return None
