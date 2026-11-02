"""dataset_versions.embedding_model: the embedding model a version's search vectors were made with (EMBEDDING_MODEL at
build time). NULL = the original multilingual MiniLM, as every version built before this column.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dataset_versions", sa.Column("embedding_model", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dataset_versions", "embedding_model")
