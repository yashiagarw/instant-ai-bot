"""Customer language on service requests (Phase 5.5): service_requests.language ("en" / "hi", nullable), set from the
web app's language switch; customer notifications use it before detecting the language from what was typed.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("service_requests", sa.Column("language", sa.String(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column("service_requests", "language")
