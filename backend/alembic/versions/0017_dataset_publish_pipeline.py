"""Dataset publish pipeline: dataset_versions gets where a version came from (import, upload for one category,
rollback), what it was built on, its validation report, diff, eval and publish details; dataset_jobs holds the
background jobs (one queued or running at a time); questions belong to a dataset version, so a draft's questions
never replace the live ones.

Existing questions move to the version their effects point at, else the version the app serves (the published
one, else the newest), else they are removed (there is nothing for them to belong to).

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "dataset_jobs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("kind", _enum("kind", "build", "eval", "publish", "rollback"), nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "status",
            _enum("status", "queued", "running", "succeeded", "failed"),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("progress", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("step", sa.Text(), server_default="", nullable=False),
        sa.Column("log", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.Text(), server_default="", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["staff_users.id"],
            name=op.f("fk_dataset_jobs_created_by_id_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_dataset_jobs_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_jobs")),
    )
    op.create_index(op.f("ix_dataset_jobs_dataset_version_id"), "dataset_jobs", ["dataset_version_id"])
    op.create_index(
        "uq_dataset_jobs_one_active",
        "dataset_jobs",
        [sa.literal_column("(true)")],
        unique=True,
        postgresql_where="status IN ('queued', 'running')",
    )

    op.add_column(
        "dataset_versions",
        sa.Column("origin", _enum("origin", "import", "upload", "rollback"), server_default="import", nullable=False),
    )
    for name, type_ in (
        ("category_code", sa.Text()),
        ("source_file_no", sa.SmallInteger()),
        ("base_version_id", sa.BigInteger()),
        ("rollback_of_id", sa.BigInteger()),
        ("upload_name", sa.Text()),
        ("created_by", sa.Text()),
    ):
        op.add_column("dataset_versions", sa.Column(name, type_, nullable=True))
    for name in ("validation", "diff", "eval"):
        op.add_column(
            "dataset_versions",
            sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        )
    op.add_column("dataset_versions", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("dataset_versions", sa.Column("published_by", sa.Text(), nullable=True))
    op.add_column("dataset_versions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("dataset_versions", sa.Column("override_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_dataset_versions_base_version_id_dataset_versions"),
        "dataset_versions",
        "dataset_versions",
        ["base_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_dataset_versions_category_code_categories"),
        "dataset_versions",
        "categories",
        ["category_code"],
        ["code"],
    )
    op.create_foreign_key(
        op.f("fk_dataset_versions_rollback_of_id_dataset_versions"),
        "dataset_versions",
        "dataset_versions",
        ["rollback_of_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("questions", sa.Column("dataset_version_id", sa.BigInteger(), nullable=True))
    op.execute(
        """
        UPDATE questions q SET dataset_version_id = (
            SELECT f.dataset_version_id FROM question_options o
            JOIN option_effects e ON e.option_id = o.id
            JOIN faults f ON f.id = e.fault_id
            WHERE o.question_id = q.id
            ORDER BY f.dataset_version_id DESC LIMIT 1
        )
        """
    )
    op.execute(
        """
        UPDATE questions SET dataset_version_id = COALESCE(
            (SELECT id FROM dataset_versions WHERE status = 'published'),
            (SELECT id FROM dataset_versions WHERE status IN ('validated', 'draft') ORDER BY id DESC LIMIT 1)
        )
        WHERE dataset_version_id IS NULL
        """
    )
    op.execute("DELETE FROM questions WHERE dataset_version_id IS NULL")
    op.alter_column("questions", "dataset_version_id", existing_type=sa.BigInteger(), nullable=False)
    op.create_index(op.f("ix_questions_dataset_version_id"), "questions", ["dataset_version_id"])
    op.create_foreign_key(
        op.f("fk_questions_dataset_version_id_dataset_versions"),
        "questions",
        "dataset_versions",
        ["dataset_version_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Questions were per category before: keep the served version's, drop the rest.
    op.execute(
        """
        DELETE FROM questions WHERE dataset_version_id <> COALESCE(
            (SELECT id FROM dataset_versions WHERE status = 'published'),
            (SELECT max(dataset_version_id) FROM questions)
        )
        """
    )
    op.drop_constraint(op.f("fk_questions_dataset_version_id_dataset_versions"), "questions", type_="foreignkey")
    op.drop_index(op.f("ix_questions_dataset_version_id"), table_name="questions")
    op.drop_column("questions", "dataset_version_id")
    for fk in ("rollback_of_id_dataset_versions", "category_code_categories", "base_version_id_dataset_versions"):
        op.drop_constraint(op.f(f"fk_dataset_versions_{fk}"), "dataset_versions", type_="foreignkey")
    for name in (
        "override_reason",
        "archived_at",
        "published_by",
        "published_at",
        "eval",
        "diff",
        "validation",
        "created_by",
        "upload_name",
        "rollback_of_id",
        "base_version_id",
        "source_file_no",
        "category_code",
        "origin",
    ):
        op.drop_column("dataset_versions", name)
    op.drop_index(
        "uq_dataset_jobs_one_active", table_name="dataset_jobs", postgresql_where="status IN ('queued', 'running')"
    )
    op.drop_index(op.f("ix_dataset_jobs_dataset_version_id"), table_name="dataset_jobs")
    op.drop_table("dataset_jobs")
