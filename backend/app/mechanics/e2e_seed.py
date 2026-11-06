"""Development only: the people for the live end-to-end test (apps/web/e2e/live-flow.spec.ts), with ready sessions.

    cd backend && uv run python -m app.mechanics.e2e_seed      # prints JSON: cookies and ids for Playwright

Makes (or reuses) a support agent "e2e-agent@im.test" and a verified, on-duty mechanic "E2E Mechanic" working pincode
110017 (+91 99999 00001), takes the mechanic off any open job, and starts a staff session and a mechanic session. The
browser test sets those cookies instead of typing codes (sign-in itself has its own tests). Refuses to run with
ENVIRONMENT=production.
"""

from __future__ import annotations

import json
import secrets
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.accounts.service import token_hash
from app.admin import service as staff_service
from app.admin.deps import STAFF_COOKIE
from app.admin.models import StaffSession
from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.mechanics import auth
from app.mechanics.models import Mechanic, MechanicZone
from app.requests.models import AssignmentStatus, RequestAssignment

AGENT_EMAIL = "e2e-agent@im.test"
MECHANIC_PHONE = "+919999900001"


def seed(session, settings) -> dict:
    agent = staff_service.find(session, AGENT_EMAIL)
    if agent is None:
        agent, _ = staff_service.create_staff(
            session,
            settings,
            staff_service.CLI,
            AGENT_EMAIL,
            "E2E Agent",
            ["support_agent"],
            password=secrets.token_urlsafe(18) + "Aa1!",
            secret=staff_service.security.new_totp_secret(),
        )
    staff_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session.add(
        StaffSession(
            staff_user_id=agent.id,
            token_hash=token_hash(staff_token),
            expires_at=now + timedelta(hours=settings.staff_session_hours),
            last_seen_at=now,
        )
    )
    mech = session.scalar(select(Mechanic).where(Mechanic.phone == MECHANIC_PHONE))
    if mech is None:
        mech = Mechanic(name="E2E Mechanic", phone=MECHANIC_PHONE, base_pincode="110017", base_area="Malviya Nagar")
        mech.zones = [MechanicZone(pincode="110017")]
        session.add(mech)
    mech.active, mech.on_duty, mech.max_jobs_per_day, mech.dev_seed = True, True, 30, True
    mech.verified_at, mech.verified_by = mech.verified_at or now, "e2e_seed"
    session.flush()
    # A clean slate: earlier runs' open jobs would count against them (not the requests themselves).
    session.execute(
        update(RequestAssignment)
        .where(RequestAssignment.mechanic_id == mech.id, RequestAssignment.status.in_(["offered", "accepted"]))
        .values(status=AssignmentStatus.withdrawn)
    )
    mech_token = auth.start_session(session, settings, mech)
    return {
        "staff_cookie": {"name": STAFF_COOKIE, "value": staff_token, "path": "/api/admin"},
        "mechanic_cookie": {"name": auth.COOKIE, "value": mech_token, "path": auth.COOKIE_PATH},
        "mechanic_id": mech.id,
        "mechanic_name": mech.name,
    }


def main() -> None:
    settings = get_settings()
    if settings.environment == "production":
        sys.exit("Refusing to create test accounts with ENVIRONMENT=production.")
    with make_session_factory(make_engine(settings.database_url)).begin() as session:
        print(json.dumps(seed(session, settings)))


if __name__ == "__main__":
    main()
