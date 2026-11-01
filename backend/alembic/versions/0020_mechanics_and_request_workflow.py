"""Mechanics and the request workflow: mechanics (skills, zones, shifts, encrypted documents), request assignments,
events (every status change), internal notes and outcomes (the confirmed fault, for training), and the new request
statuses (submitted, triaged, offered, accepted, en_route, arrived, in_progress, completed, cancelled, escalated).

Existing requests: new / contacted become triaged, assigned becomes accepted; safety_level is high for urgent ones;
category_code comes from the diagnosis's top cause; each gets a "submitted" event (and one for its current status).

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = "submitted, triaged, offered, accepted, en_route, arrived, in_progress, completed, cancelled, escalated"
OLD = "submitted, new, contacted, assigned, completed, cancelled"


def upgrade() -> None:
    op.execute("ALTER TABLE service_requests DROP CONSTRAINT ck_service_requests_status")
    op.execute("UPDATE service_requests SET status = 'triaged' WHERE status IN ('new', 'contacted')")
    op.execute("UPDATE service_requests SET status = 'accepted' WHERE status = 'assigned'")
    quoted = ", ".join(f"'{v.strip()}'" for v in NEW.split(","))
    op.create_check_constraint("status", "service_requests", f"status IN ({quoted})")
    op.create_table(
        "mechanics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("staff_user_id", sa.UUID(), nullable=True),
        sa.Column("base_pincode", sa.Text(), nullable=False),
        sa.Column("base_area", sa.Text(), server_default="", nullable=False),
        sa.Column("rating", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("max_jobs_per_day", sa.SmallInteger(), server_default="4", nullable=False),
        sa.Column("on_duty", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("on_duty_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("dev_seed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("base_pincode ~ '^[0-9]{6}$'", name=op.f("ck_mechanics_base_pincode_format")),
        sa.CheckConstraint("max_jobs_per_day BETWEEN 1 AND 30", name=op.f("ck_mechanics_max_jobs_range")),
        sa.CheckConstraint("rating IS NULL OR rating BETWEEN 0 AND 5", name=op.f("ck_mechanics_rating_range")),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_mechanics_staff_user_id_staff_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mechanics")),
        sa.UniqueConstraint("staff_user_id", name=op.f("uq_mechanics_staff_user_id")),
    )
    op.create_table(
        "mechanic_availability",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("mechanic_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.CheckConstraint("end_time > start_time", name=op.f("ck_mechanic_availability_shift_order")),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name=op.f("ck_mechanic_availability_weekday_range")),
        sa.ForeignKeyConstraint(
            ["mechanic_id"],
            ["mechanics.id"],
            name=op.f("fk_mechanic_availability_mechanic_id_mechanics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mechanic_availability")),
    )
    op.create_index(
        op.f("ix_mechanic_availability_mechanic_id"), "mechanic_availability", ["mechanic_id"], unique=False
    )
    op.create_table(
        "mechanic_documents",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("mechanic_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "id_proof",
                "driving_licence",
                "certificate",
                "other",
                name="kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["mechanic_id"],
            ["mechanics.id"],
            name=op.f("fk_mechanic_documents_mechanic_id_mechanics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mechanic_documents")),
    )
    op.create_index(op.f("ix_mechanic_documents_mechanic_id"), "mechanic_documents", ["mechanic_id"], unique=False)
    op.create_table(
        "mechanic_skills",
        sa.Column("mechanic_id", sa.Integer(), nullable=False),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_code"],
            ["categories.code"],
            name=op.f("fk_mechanic_skills_category_code_categories"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mechanic_id"], ["mechanics.id"], name=op.f("fk_mechanic_skills_mechanic_id_mechanics"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("mechanic_id", "category_code", name=op.f("pk_mechanic_skills")),
    )
    op.create_table(
        "mechanic_zones",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("mechanic_id", sa.Integer(), nullable=False),
        sa.Column("pincode", sa.Text(), nullable=True),
        sa.Column("radius_km", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("center_lat", sa.Numeric(precision=8, scale=5), nullable=True),
        sa.Column("center_lon", sa.Numeric(precision=8, scale=5), nullable=True),
        sa.CheckConstraint("pincode IS NULL OR pincode ~ '^[0-9]{6}$'", name=op.f("ck_mechanic_zones_pincode_format")),
        sa.CheckConstraint(
            "(pincode IS NOT NULL) <> (radius_km IS NOT NULL)", name=op.f("ck_mechanic_zones_pincode_or_radius")
        ),
        sa.CheckConstraint(
            "radius_km IS NULL OR radius_km BETWEEN 0.5 AND 100", name=op.f("ck_mechanic_zones_radius_range")
        ),
        sa.ForeignKeyConstraint(
            ["mechanic_id"], ["mechanics.id"], name=op.f("fk_mechanic_zones_mechanic_id_mechanics"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mechanic_zones")),
        sa.UniqueConstraint("mechanic_id", "pincode", name=op.f("uq_mechanic_zones_mechanic_id_pincode")),
    )
    op.create_index(op.f("ix_mechanic_zones_mechanic_id"), "mechanic_zones", ["mechanic_id"], unique=False)
    op.create_table(
        "request_assignments",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("mechanic_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "offered",
                "accepted",
                "declined",
                "withdrawn",
                "completed",
                name="status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="offered",
            nullable=False,
        ),
        sa.Column("offered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offered_by_id", sa.UUID(), nullable=True),
        sa.Column("offered_by", sa.Text(), server_default="", nullable=False),
        sa.Column("match", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["mechanic_id"],
            ["mechanics.id"],
            name=op.f("fk_request_assignments_mechanic_id_mechanics"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["offered_by_id"],
            ["staff_users.id"],
            name=op.f("fk_request_assignments_offered_by_id_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["service_requests.id"],
            name=op.f("fk_request_assignments_request_id_service_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_assignments")),
    )
    op.create_index(op.f("ix_request_assignments_mechanic_id"), "request_assignments", ["mechanic_id"], unique=False)
    op.create_index(op.f("ix_request_assignments_request_id"), "request_assignments", ["request_id"], unique=False)
    op.create_index(
        "uq_request_assignments_one_open",
        "request_assignments",
        ["request_id"],
        unique=True,
        postgresql_where="status IN ('offered', 'accepted')",
    )
    op.create_table(
        "request_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "status",
                "offer",
                "response",
                "agent",
                "outcome",
                name="kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_label", sa.Text(), server_default="", nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["staff_users.id"], name=op.f("fk_request_events_actor_id_staff_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["service_requests.id"],
            name=op.f("fk_request_events_request_id_service_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_events")),
    )
    op.create_index(op.f("ix_request_events_request_id"), "request_events", ["request_id"], unique=False)
    op.create_table(
        "request_notes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("author_label", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"], ["staff_users.id"], name=op.f("fk_request_notes_author_id_staff_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["service_requests.id"],
            name=op.f("fk_request_notes_request_id_service_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_notes")),
    )
    op.create_index(op.f("ix_request_notes_request_id"), "request_notes", ["request_id"], unique=False)
    op.create_table(
        "request_outcomes",
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("confirmed_fault_key", sa.Text(), nullable=True),
        sa.Column("other_text", sa.Text(), server_default="", nullable=False),
        sa.Column("ai_top1", sa.Boolean(), nullable=True),
        sa.Column("ai_top3", sa.Boolean(), nullable=True),
        sa.Column("ai_ranked", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("parts_used", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("final_cost_inr", sa.Integer(), nullable=True),
        sa.Column("mechanic_notes", sa.Text(), server_default="", nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=True),
        sa.Column("mechanic_id", sa.Integer(), nullable=True),
        sa.Column("recorded_by", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "confirmed_fault_key IS NOT NULL OR length(btrim(other_text)) > 0",
            name=op.f("ck_request_outcomes_fault_or_other"),
        ),
        sa.CheckConstraint(
            "final_cost_inr IS NULL OR final_cost_inr >= 0", name=op.f("ck_request_outcomes_cost_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_request_outcomes_dataset_version_id_dataset_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["mechanic_id"],
            ["mechanics.id"],
            name=op.f("fk_request_outcomes_mechanic_id_mechanics"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["service_requests.id"],
            name=op.f("fk_request_outcomes_request_id_service_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["diagnosis_sessions.id"],
            name=op.f("fk_request_outcomes_session_id_diagnosis_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("request_id", name=op.f("pk_request_outcomes")),
    )
    op.add_column(
        "service_requests",
        sa.Column(
            "safety_level",
            sa.Enum("none", "low", "medium", "high", name="safety_level", native_enum=False, create_constraint=True),
            server_default="none",
            nullable=False,
        ),
    )
    op.add_column("service_requests", sa.Column("category_code", sa.Text(), nullable=True))
    op.add_column("service_requests", sa.Column("assigned_agent_id", sa.UUID(), nullable=True))
    op.add_column("service_requests", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column(  # "in_progress" is longer than the old longest value
        "service_requests", "status", existing_type=sa.VARCHAR(length=9), type_=sa.String(length=11), existing_nullable=False
    )
    op.create_foreign_key(
        op.f("fk_service_requests_assigned_agent_id_staff_users"),
        "service_requests",
        "staff_users",
        ["assigned_agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_service_requests_category_code_categories"),
        "service_requests",
        "categories",
        ["category_code"],
        ["code"],
        ondelete="SET NULL",
    )
    op.execute("UPDATE service_requests SET safety_level = 'high' WHERE urgent")
    op.execute(
        """
        UPDATE service_requests r SET category_code = f.category_code
        FROM session_results sr JOIN faults f ON f.id = sr.fault_id
        WHERE sr.session_id = r.session_id AND sr.rank = 1
        """
    )
    op.execute(
        """
        INSERT INTO request_events (request_id, at, kind, to_status, actor_label)
        SELECT id, created_at, 'status', 'submitted', 'customer' FROM service_requests
        """
    )
    op.execute(
        """
        INSERT INTO request_events (request_id, at, kind, from_status, to_status, actor_label, note)
        SELECT id, created_at, 'status', 'submitted', status, 'migration 0020', 'status before the workflow'
        FROM service_requests WHERE status <> 'submitted'
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE service_requests DROP CONSTRAINT ck_service_requests_status")
    op.execute("UPDATE service_requests SET status = 'contacted' WHERE status IN ('triaged', 'escalated')")
    op.execute(
        "UPDATE service_requests SET status = 'assigned' "
        "WHERE status IN ('offered', 'accepted', 'en_route', 'arrived', 'in_progress')"
    )
    quoted = ", ".join(f"'{v.strip()}'" for v in OLD.split(","))
    op.create_check_constraint("status", "service_requests", f"status IN ({quoted})")
    op.drop_constraint(op.f("fk_service_requests_category_code_categories"), "service_requests", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_service_requests_assigned_agent_id_staff_users"), "service_requests", type_="foreignkey"
    )
    op.alter_column(
        "service_requests", "status", existing_type=sa.String(length=11), type_=sa.VARCHAR(length=9), existing_nullable=False
    )
    op.drop_column("service_requests", "status_changed_at")
    op.drop_column("service_requests", "assigned_agent_id")
    op.drop_column("service_requests", "category_code")
    op.drop_column("service_requests", "safety_level")
    op.drop_table("request_outcomes")
    op.drop_index(op.f("ix_request_notes_request_id"), table_name="request_notes")
    op.drop_table("request_notes")
    op.drop_index(op.f("ix_request_events_request_id"), table_name="request_events")
    op.drop_table("request_events")
    op.drop_index(
        "uq_request_assignments_one_open",
        table_name="request_assignments",
        postgresql_where="status IN ('offered', 'accepted')",
    )
    op.drop_index(op.f("ix_request_assignments_request_id"), table_name="request_assignments")
    op.drop_index(op.f("ix_request_assignments_mechanic_id"), table_name="request_assignments")
    op.drop_table("request_assignments")
    op.drop_index(op.f("ix_mechanic_zones_mechanic_id"), table_name="mechanic_zones")
    op.drop_table("mechanic_zones")
    op.drop_table("mechanic_skills")
    op.drop_index(op.f("ix_mechanic_documents_mechanic_id"), table_name="mechanic_documents")
    op.drop_table("mechanic_documents")
    op.drop_index(op.f("ix_mechanic_availability_mechanic_id"), table_name="mechanic_availability")
    op.drop_table("mechanic_availability")
    op.drop_table("mechanics")
