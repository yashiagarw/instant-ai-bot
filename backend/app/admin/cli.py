"""Staff accounts from the command line (run from backend/). Every change is written to the audit log as "cli".

    uv run python -m app.admin.cli create-super-admin --email you@example.com --name "Your Name"
    uv run python -m app.admin.cli reset-two-factor --email you@example.com    # lost phone: set up again on sign-in
    uv run python -m app.admin.cli unlock --email you@example.com              # after too many wrong tries
    uv run python -m app.admin.cli reset-password --email you@example.com      # forgotten password

reset-password asks for the new password twice (not shown; never an argument), with the same rules as
create-super-admin. It also unlocks the account and signs out its sessions; two-factor stays as it is.

create-super-admin asks for a password (twice, not shown), prints a QR code and the secret for the authenticator
app ONCE, and saves the account only after you type a current 6-digit code from the app. It refuses when an active
super admin already exists (add more staff from /api/admin/staff instead), unless --another.
"""

from __future__ import annotations

import argparse
import getpass
import io
import sys
from collections.abc import Callable

import qrcode
from sqlalchemy.orm import Session

from app.admin import security
from app.admin import service as staff
from app.admin.models import RoleCode
from app.config import Settings

Ask = Callable[[str], str]
Out = Callable[[str], None]
CODE_TRIES = 3


def qr_text(uri: str) -> str:
    qr = qrcode.QRCode(border=2)
    qr.add_data(uri)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    return buf.getvalue()


def show_two_factor(settings: Settings, secret: str, email: str, out: Out) -> None:
    uri = security.provisioning_uri(settings, secret, email)
    out("\nTwo-factor setup (shown only now). In Google Authenticator: + > Scan a QR code:\n")
    out(qr_text(uri))
    grouped = " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))
    out(f"Or + > Enter a setup key. Account: {email}  Key: {grouped}  (time based)")
    out(f"otpauth URI: {uri}\n")


def confirm_code(secret: str, ask: Ask, out: Out) -> int | None:
    for _ in range(CODE_TRIES):
        step = security.totp_step(secret, ask("Type the 6-digit code the app shows now: "), None)
        if step is not None:
            return step
        out("That code doesn't match. Check the phone's time is automatic, and try the newest code.")
    return None


def ask_password(email: str, ask_secret: Ask, out: Out) -> str | None:
    for _ in range(3):
        pw = ask_secret(f"Password (at least {security.MIN_PASSWORD} characters, not shown): ")
        try:
            security.check_password_policy(pw, email)
        except security.WeakPassword as e:
            out(str(e))
            continue
        if ask_secret("Same password again: ") == pw:
            return pw
        out("The passwords differ.")
    return None


def create_super_admin(
    session: Session, settings: Settings, email: str, name: str, ask: Ask, ask_secret: Ask, out: Out,
    another: bool = False,
) -> int:  # fmt: skip
    email = staff.normalize_email(email)
    if staff.active_super_admins(session) and not another:
        out("An active super admin already exists. Sign in and add staff from /api/admin/staff (or use --another).")
        return 1
    if staff.find(session, email):
        out(f"{email} already has a staff account.")
        return 1
    password = ask_password(email, ask_secret, out)
    if password is None:
        return 1
    secret = security.new_totp_secret()
    show_two_factor(settings, secret, email, out)
    step = confirm_code(secret, ask, out)
    if step is None:
        out("Not saved. Run the command again to start over.")
        return 1
    user, _ = staff.create_staff(
        session, settings, staff.CLI, email, name, [RoleCode.super_admin], password=password, secret=secret
    )
    user.totp_last_step = step  # the code just typed cannot be used again to sign in
    session.commit()
    out(f"Super admin {email} created. Sign in with POST /api/admin/auth/login (email, password, a new code).")
    return 0


def reset_two_factor(session: Session, email: str, out: Out) -> int:
    """Remove two-factor (lost phone). The next sign-in in the admin app shows a new QR code and asks for a code."""
    user = staff.find(session, email)
    if user is None:
        out(f"No staff account for {email}.")
        return 1
    staff.reset_two_factor(session, staff.CLI, user)
    session.commit()
    out(
        f"Two-factor removed for {user.email} and its sessions signed out. Sign in at the admin app "
        "(http://localhost:3001/login locally): it shows a new QR code once, then asks for a code."
    )
    return 0


def reset_password(session: Session, email: str, ask_secret: Ask, out: Out) -> int:
    user = staff.find(session, email)
    if user is None:
        out(f"No staff account for {email}.")
        return 1
    password = ask_password(user.email, ask_secret, out)
    if password is None:
        out("Password not changed.")
        return 1
    staff.reset_password(session, staff.CLI, user, password)
    session.commit()
    out(f"New password set for {user.email}; it is unlocked and its sessions are signed out. Two-factor is unchanged.")
    return 0


def unlock(session: Session, email: str, out: Out) -> int:
    user = staff.find(session, email)
    if user is None:
        out(f"No staff account for {email}.")
        return 1
    staff.unlock(session, staff.CLI, user)
    session.commit()
    out(f"{user.email} unlocked.")
    return 0


def main(argv: list[str] | None = None, ask: Ask = input, ask_secret: Ask = getpass.getpass, out: Out = print) -> int:
    from app.config import get_settings
    from app.db import make_engine, make_session_factory

    ap = argparse.ArgumentParser(prog="python -m app.admin.cli", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create-super-admin")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--another", action="store_true", help="even though an active super admin exists")
    for name in ("reset-two-factor", "unlock", "reset-password"):
        sub.add_parser(name).add_argument("--email", required=True)
    args = ap.parse_args(argv)

    settings = get_settings()
    with make_session_factory(make_engine(settings.database_url))() as session:
        try:
            if args.command == "create-super-admin":
                return create_super_admin(session, settings, args.email, args.name, ask, ask_secret, out, args.another)
            if args.command == "reset-two-factor":
                return reset_two_factor(session, args.email, out)
            if args.command == "reset-password":
                return reset_password(session, args.email, ask_secret, out)
            return unlock(session, args.email, out)
        except staff.StaffError as e:
            out(str(e))
            return 1


if __name__ == "__main__":
    sys.exit(main())
