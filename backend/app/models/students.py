import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CourseStrategy


class StudentProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_profiles"

    ra: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    admission_year: Mapped[int]
    admission_shift: Mapped[str | None] = mapped_column(String(32))
    campus: Mapped[str | None] = mapped_column(String(32))
    cr: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    ca: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    max_quarter_credits: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    accumulated_credits: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    course_strategy: Mapped[CourseStrategy] = mapped_column(
        Enum(CourseStrategy, native_enum=False, length=48),
        default=CourseStrategy.PRIMARY_COURSE,
    )

    courses: Mapped[list["StudentCourse"]] = relationship(
        back_populates="student_profile", cascade="all, delete-orphan"
    )
    completed_subjects: Mapped[list["StudentCompletedSubject"]] = relationship(
        back_populates="student_profile", cascade="all, delete-orphan"
    )
    in_progress_subjects: Mapped[list["StudentInProgressSubject"]] = relationship(
        back_populates="student_profile", cascade="all, delete-orphan"
    )
    preferences: Mapped["StudentPreference | None"] = relationship(
        back_populates="student_profile",
        cascade="all, delete-orphan",
        uselist=False,
    )
    history_import: Mapped["StudentHistoryImport | None"] = relationship(
        back_populates="student_profile",
        cascade="all, delete-orphan",
        uselist=False,
    )


class StudentCourse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_courses"
    __table_args__ = (
        UniqueConstraint("student_profile_id", "course_id", name="uq_student_course"),
        Index("ix_student_courses_curriculum", "curriculum_version_id", "student_profile_id"),
    )

    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    curriculum_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="RESTRICT"), index=True
    )
    is_primary: Mapped[bool] = mapped_column(default=False)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    cp: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))

    student_profile: Mapped[StudentProfile] = relationship(back_populates="courses")
    course: Mapped["Course"] = relationship()  # noqa: F821
    curriculum_version: Mapped["CurriculumVersion"] = relationship()  # noqa: F821


class StudentCompletedSubject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_completed_subjects"
    __table_args__ = (
        UniqueConstraint("student_profile_id", "subject_id", name="uq_student_completed_subject"),
    )

    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), index=True
    )
    term_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("terms.id", ondelete="SET NULL"), index=True
    )
    grade: Mapped[str | None] = mapped_column(String(8))
    credits: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    student_profile: Mapped[StudentProfile] = relationship(back_populates="completed_subjects")
    subject: Mapped["Subject"] = relationship()  # noqa: F821
    term: Mapped["Term | None"] = relationship()  # noqa: F821


class StudentInProgressSubject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_in_progress_subjects"
    __table_args__ = (
        UniqueConstraint("student_profile_id", "subject_id", name="uq_student_progress_subject"),
    )

    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), index=True
    )
    term_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("terms.id", ondelete="SET NULL"), index=True
    )

    student_profile: Mapped[StudentProfile] = relationship(back_populates="in_progress_subjects")
    subject: Mapped["Subject"] = relationship()  # noqa: F821
    term: Mapped["Term | None"] = relationship()  # noqa: F821


class StudentPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_preferences"

    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), unique=True, index=True
    )
    hard_constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    soft_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    student_profile: Mapped[StudentProfile] = relationship(back_populates="preferences")


class StudentHistoryImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_history_imports"

    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), unique=True, index=True
    )
    ra: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(32))
    page_count: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    student_profile: Mapped[StudentProfile] = relationship(back_populates="history_import")


from app.models.curriculum import Course, CurriculumVersion  # noqa: E402
from app.models.imports import Term  # noqa: E402
from app.models.offerings import Subject  # noqa: E402
