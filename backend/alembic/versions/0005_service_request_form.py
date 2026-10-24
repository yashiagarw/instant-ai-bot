"""Request a Mechanic form: reference number, urgency, service type, location, time, notes, email alert record.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUS = ["new", "contacted", "assigned", "completed", "cancelled"]
NEW_STATUS = ["submitted", *OLD_STATUS]


def _in(column: str, values: list[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("service_requests", sa.Column("reference", sa.Text(), nullable=True))
    # Existing rows (none expected) get a reference from their id.
    op.execute(
        "UPDATE service_requests SET reference = 'IM-' || upper(substr(md5(id::text), 1, 6)) WHERE reference IS NULL"
    )
    op.alter_column("service_requests", "reference", nullable=False)
    op.create_unique_constraint(op.f("uq_service_requests_reference"), "service_requests", ["reference"])

    op.add_column("service_requests", sa.Column("urgent", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column(
        "service_requests",
        sa.Column("service_type", sa.String(length=11), nullable=False, server_default="at_location"),
    )
    op.create_check_constraint(
        op.f("ck_service_requests_service_type"),
        "service_requests",
        _in("service_type", ["at_location", "tow", "workshop"]),
    )
    for name in ("pincode", "address", "preferred_time", "notes"):
        op.add_column("service_requests", sa.Column(name, sa.Text(), nullable=False, server_default=""))
    op.add_column("service_requests", sa.Column("alert_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("service_requests", sa.Column("alert_error", sa.Text(), nullable=True))

    op.drop_constraint(op.f("ck_service_requests_status"), "service_requests", type_="check")
    op.create_check_constraint(op.f("ck_service_requests_status"), "service_requests", _in("status", NEW_STATUS))
    op.alter_column("service_requests", "status", server_default="submitted")


def downgrade() -> None:
    op.execute("UPDATE service_requests SET status = 'new' WHERE status = 'submitted'")
    op.alter_column("service_requests", "status", server_default="new")
    op.drop_constraint(op.f("ck_service_requests_status"), "service_requests", type_="check")
    op.create_check_constraint(op.f("ck_service_requests_status"), "service_requests", _in("status", OLD_STATUS))
    for name in ("alert_error", "alert_sent_at", "notes", "preferred_time", "address", "pincode"):
        op.drop_column("service_requests", name)
    op.drop_constraint(op.f("ck_service_requests_service_type"), "service_requests", type_="check")
    op.drop_column("service_requests", "service_type")
    op.drop_column("service_requests", "urgent")
    op.drop_constraint(op.f("uq_service_requests_reference"), "service_requests", type_="unique")
    op.drop_column("service_requests", "reference")
