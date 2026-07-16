"""add student RA and quarter credit limit

Revision ID: a91e6c1f42d8
Revises: 6f2e8d1c4a90
Create Date: 2026-07-16 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a91e6c1f42d8"
down_revision: str | None = "6f2e8d1c4a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "student_profiles",
        sa.Column("ra", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "student_profiles",
        sa.Column("max_quarter_credits", sa.Numeric(precision=6, scale=2), nullable=True),
    )
    op.create_index("ix_student_profiles_ra", "student_profiles", ["ra"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_student_profiles_ra", table_name="student_profiles")
    op.drop_column("student_profiles", "max_quarter_credits")
    op.drop_column("student_profiles", "ra")
