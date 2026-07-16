import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import StatisticsConfidence


class GradeStatisticsMixin:
    grade_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    effective_sample_size: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    raw_a_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    adjusted_a_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    raw_ab_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    adjusted_ab_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    raw_failure_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    adjusted_failure_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    raw_fo_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    adjusted_fo_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    raw_mean_grade: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    adjusted_mean_grade: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    confidence: Mapped[StatisticsConfidence] = mapped_column(
        Enum(StatisticsConfidence, native_enum=False, length=16),
        default=StatisticsConfidence.NONE,
    )
    prior_weight: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    reference_rates: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    grade_weights: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    source_fetched_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class StatisticsBuild(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "statistics_builds"

    prior_weight: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    grade_weights: Mapped[dict[str, float]] = mapped_column(JSON)
    teacher_statistics_count: Mapped[int] = mapped_column(Integer, default=0)
    subject_statistics_count: Mapped[int] = mapped_column(Integer, default=0)
    teacher_subject_statistics_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_history_available: Mapped[bool] = mapped_column(default=False)
    source_snapshot_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class TeacherStatistics(
    GradeStatisticsMixin,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "teacher_statistics"

    teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"), index=True
    )
    external_teacher_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teacher_review_snapshots.id", ondelete="SET NULL"), index=True
    )


class SubjectStatistics(
    GradeStatisticsMixin,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "subject_statistics"

    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )
    external_subject_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subject_review_snapshots.id", ondelete="SET NULL"), index=True
    )


class TeacherSubjectStatistics(
    GradeStatisticsMixin,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "teacher_subject_statistics"
    __table_args__ = (
        Index(
            "uq_teacher_subject_statistics_external",
            "external_teacher_id",
            "external_subject_id",
            unique=True,
        ),
        Index("ix_teacher_subject_statistics_internal", "teacher_id", "subject_id"),
    )

    teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"), index=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )
    external_teacher_id: Mapped[str] = mapped_column(String(255), index=True)
    external_subject_id: Mapped[str] = mapped_column(String(255), index=True)
    source_teacher_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teacher_review_snapshots.id", ondelete="SET NULL"), index=True
    )
    source_subject_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subject_review_snapshots.id", ondelete="SET NULL"), index=True
    )


class TeacherTermStatistics(
    GradeStatisticsMixin,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "teacher_term_statistics"
    __table_args__ = (
        Index(
            "uq_teacher_term_statistics_external",
            "external_teacher_id",
            "external_subject_id",
            "term_id",
            unique=True,
        ),
    )

    term_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("terms.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"), index=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )
    external_teacher_id: Mapped[str] = mapped_column(String(255), index=True)
    external_subject_id: Mapped[str | None] = mapped_column(String(255), index=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
