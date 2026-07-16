"""add student CA

Revision ID: 6f2e8d1c4a90
Revises: ed7692a809a4
Create Date: 2026-07-16 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6f2e8d1c4a90"
down_revision: str | None = "ed7692a809a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "student_profiles",
        sa.Column("ca", sa.Numeric(precision=6, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("student_profiles", "ca")
