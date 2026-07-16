"""add student history imports

Revision ID: c4d8a0e2b719
Revises: a91e6c1f42d8
Create Date: 2026-07-16 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d8a0e2b719"
down_revision: str | None = "a91e6c1f42d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_history_imports",
        sa.Column("student_profile_id", sa.Uuid(), nullable=False),
        sa.Column("ra", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extracted_data", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_profile_id"],
            ["student_profiles.id"],
            name=op.f("fk_student_history_imports_student_profile_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_history_imports")),
    )
    op.create_index(
        op.f("ix_student_history_imports_ra"),
        "student_history_imports",
        ["ra"],
        unique=True,
    )
    op.create_index(
        op.f("ix_student_history_imports_student_profile_id"),
        "student_history_imports",
        ["student_profile_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_student_history_imports_student_profile_id"),
        table_name="student_history_imports",
    )
    op.drop_index(op.f("ix_student_history_imports_ra"), table_name="student_history_imports")
    op.drop_table("student_history_imports")
