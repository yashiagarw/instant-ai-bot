"""Fake mechanics for development only: `uv run python -m app.mechanics.dev_seed`. Refuses to run when
ENVIRONMENT=production. Names are clearly fake ("<first name> Demo-Mechanic"; customers see the first name only)
and phone numbers are +91 90000 0000X. Running it again updates the same rows (matched by phone); --remove deletes
them."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, time
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.knowledge.models import Category
from app.mechanics.models import Mechanic, MechanicAvailability, MechanicSkill, MechanicZone

ALL_DAY = [(d, time(0, 0), time(23, 59)) for d in range(7)]
FAKE = [
    # name, phone, base pincode, area, rating, max jobs, skills, zones (pincodes or radius km), shifts
    ("Arjun Demo-Mechanic", "+919000000001", "110017", "Malviya Nagar (fake)", "4.6", 5,
     ["battery", "not_starting", "brakes", "ac", "tyre", "engine"], {"radius": 12}, ALL_DAY),
    ("Bina Demo-Mechanic", "+919000000002", "201301", "Noida Sector 18 (fake)", "4.2", 4,
     ["battery", "electrical", "lights_horn", "ac", "self_start"],
     {"pincodes": ["201301", "201303", "201304", "201309"]}, ALL_DAY),
    ("Chetan Demo-Mechanic", "+919000000003", "122002", "Gurugram DLF (fake)", "3.9", 3,
     ["brakes", "suspension", "steering", "tyre", "clutch", "gearbox"], {"radius": 15}, ALL_DAY),
    ("Divya Demo-Mechanic", "+919000000004", "110092", "Preet Vihar (fake)", None, 4,
     ["cooling", "engine", "hose_leak", "towing_accident", "key_lockout"], {"radius": 10},
     [(d, time(9, 0), time(18, 0)) for d in range(6)]),
    ("Ehsan Demo-Mechanic", "+919000000005", "121001", "Faridabad (fake)", "4.8", 6,
     ["battery", "not_starting", "tyre", "fuel_delivery", "stuck"], {"radius": 20}, ALL_DAY),
]  # fmt: skip


def seed(session: Session) -> list[Mechanic]:
    known = set(session.scalars(select(Category.code)))
    out = []
    for name, phone, pin, area, rating, max_jobs, skills, zones, shifts in FAKE:
        m = session.scalar(select(Mechanic).where(Mechanic.phone == phone, Mechanic.dev_seed))
        if m is None:
            m = Mechanic(phone=phone, dev_seed=True)
            session.add(m)
        m.name, m.base_pincode, m.base_area, m.max_jobs_per_day = name, pin, area, max_jobs
        m.rating = Decimal(rating) if rating else None
        m.on_duty, m.active, m.notes = True, True, "Fake mechanic for development (app.mechanics.dev_seed)."
        if m.verified_at is None:  # can sign in to the mechanic app locally (phone code printed by the console SMS)
            m.verified_at, m.verified_by = datetime.now(UTC), "dev_seed"
        m.skills.clear(), m.zones.clear(), m.shifts.clear()
        session.flush()  # delete the old rows before adding the same pincodes again
        m.skills = [MechanicSkill(category_code=c) for c in skills if c in known]
        m.zones = (
            [MechanicZone(pincode=p) for p in zones["pincodes"]]
            if "pincodes" in zones
            else [MechanicZone(radius_km=Decimal(zones["radius"]))]
        )
        m.shifts = [MechanicAvailability(weekday=d, start_time=a, end_time=b) for d, a, b in shifts]
        session.flush()
        out.append(m)
    return out


def remove(session: Session) -> int:
    return session.execute(delete(Mechanic).where(Mechanic.dev_seed)).rowcount


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true", help="delete the fake mechanics")
    args = parser.parse_args(argv)
    settings = get_settings()
    if settings.environment == "production":
        print("Refusing to seed fake mechanics in production.", file=sys.stderr)
        return 2
    engine = make_engine(settings.database_url, settings.db_connect_timeout)
    with make_session_factory(engine)() as session:
        if args.remove:
            n = remove(session)
            session.commit()
            print(f"Removed {n} fake mechanics.")
            return 0
        rows = seed(session)
        session.commit()
        for m in rows:
            print(f"  {m.id:>3}  {m.name:<22} base {m.base_pincode}  on duty")
        print(f"Seeded {len(rows)} fake mechanics (development only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
