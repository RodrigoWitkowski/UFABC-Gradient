"""guard concurrent UFABC Next sync runs

Revision ID: d73c1a9b52ef
Revises: c4d8a0e2b719
Create Date: 2026-07-16 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d73c1a9b52ef"
down_revision: str | None = "c4d8a0e2b719"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_next_sync_runs_single_running",
        "ufabc_next_sync_runs",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_next_sync_runs_single_running",
        table_name="ufabc_next_sync_runs",
    )
