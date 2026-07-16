import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ExternalSyncStatus


class ExternalSubjectIdentifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "external_subject_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_id",
            "subject_id",
            name="uq_subject_external_provider_id_subject",
        ),
    )

    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(255))


class UfabcNextSyncRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ufabc_next_sync_runs"
    __table_args__ = (Index("ix_next_sync_runs_season_created", "season", "created_at"),)

    season: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[ExternalSyncStatus] = mapped_column(
        Enum(ExternalSyncStatus, native_enum=False, length=32),
        default=ExternalSyncStatus.RUNNING,
        index=True,
    )
    include_teacher_reviews: Mapped[bool] = mapped_column(Boolean, default=False)
    include_subject_reviews: Mapped[bool] = mapped_column(Boolean, default=False)
    force_refresh: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    remote_requests: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    components_received: Mapped[int] = mapped_column(Integer, default=0)
    components_matched: Mapped[int] = mapped_column(Integer, default=0)
    components_unmatched: Mapped[int] = mapped_column(Integer, default=0)
    teacher_reviews_synced: Mapped[int] = mapped_column(Integer, default=0)
    subject_reviews_synced: Mapped[int] = mapped_column(Integer, default=0)
    request_log: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)


class UfabcNextComponentSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ufabc_next_component_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "sync_run_id",
            "external_section_code",
            name="uq_next_component_snapshot_run_section",
        ),
        Index("ix_next_component_snapshots_term_section", "term_id", "section_id"),
        Index("ix_next_component_snapshots_external_subject", "external_subject_id"),
    )

    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ufabc_next_sync_runs.id", ondelete="CASCADE"), index=True
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("terms.id", ondelete="RESTRICT"), index=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sections.id", ondelete="SET NULL"), index=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )
    external_component_id: Mapped[str | None] = mapped_column(String(255), index=True)
    external_section_code: Mapped[str] = mapped_column(String(64), index=True)
    external_subject_id: Mapped[str | None] = mapped_column(String(255))
    seats: Mapped[int | None]
    requests: Mapped[int | None]
    enrolled_count: Mapped[int] = mapped_column(Integer, default=0)
    ideal_term: Mapped[bool | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class TeacherReviewSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teacher_review_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "sync_run_id",
            "external_teacher_id",
            name="uq_teacher_review_snapshot_run_teacher",
        ),
        Index("ix_teacher_review_snapshots_teacher_fetched", "teacher_id", "fetched_at"),
    )

    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ufabc_next_sync_runs.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"), index=True
    )
    external_teacher_id: Mapped[str] = mapped_column(String(255), index=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    distribution: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    specific_statistics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class SubjectReviewSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subject_review_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "sync_run_id",
            "external_subject_id",
            name="uq_subject_review_snapshot_run_subject",
        ),
        Index("ix_subject_review_snapshots_subject_fetched", "subject_id", "fetched_at"),
    )

    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ufabc_next_sync_runs.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )
    external_subject_id: Mapped[str] = mapped_column(String(255), index=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    distribution: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    teacher_statistics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class UfabcNextCacheEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ufabc_next_cache_entries"

    request_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    path: Mapped[str] = mapped_column(String(512))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status_code: Mapped[int]
    response_body: Mapped[Any] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
