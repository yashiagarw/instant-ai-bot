"""Embeddings for fault items (symptoms), used for free-text matching.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("fault_items", sa.Column("embedding", Vector(dim=384), nullable=True))
    op.create_index(
        "ix_fault_items_embedding_hnsw",
        "fault_items",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_fault_items_embedding_hnsw", table_name="fault_items")
    op.drop_column("fault_items", "embedding")
