import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CurriculumCategory, CurriculumCategorySource


class Course(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "courses"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512))
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")

    curriculum_versions: Mapped[list["CurriculumVersion"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    section_offerings: Mapped[list["SectionCourseOffering"]] = relationship(  # noqa: F821
        back_populates="course"
    )


class CurriculumVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_versions"
    __table_args__ = (
        UniqueConstraint("course_id", "version", name="uq_curriculum_course_version"),
        Index("ix_curriculum_versions_validity", "course_id", "valid_from", "valid_until"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(64), index=True)
    admission_year_start: Mapped[int | None]
    admission_year_end: Mapped[int | None]
    valid_from: Mapped[date | None]
    valid_until: Mapped[date | None]
    unlisted_subject_category: Mapped[CurriculumCategory | None] = mapped_column(
        Enum(CurriculumCategory, native_enum=False, length=32)
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    course: Mapped[Course] = relationship(back_populates="curriculum_versions")
    subjects: Mapped[list["CourseCurriculumSubject"]] = relationship(
        back_populates="curriculum_version", cascade="all, delete-orphan"
    )
    requirements: Mapped[list["CurriculumRequirement"]] = relationship(
        back_populates="curriculum_version", cascade="all, delete-orphan"
    )


class CourseCurriculumSubject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "course_curriculum_subjects"
    __table_args__ = (
        UniqueConstraint("curriculum_version_id", "subject_id", name="uq_curriculum_subject"),
        Index("ix_curriculum_subjects_category", "curriculum_version_id", "category"),
    )

    curriculum_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), index=True
    )
    category: Mapped[CurriculumCategory] = mapped_column(
        Enum(CurriculumCategory, native_enum=False, length=32)
    )
    category_source: Mapped[CurriculumCategorySource] = mapped_column(
        Enum(CurriculumCategorySource, native_enum=False, length=32),
        default=CurriculumCategorySource.EXPLICIT,
    )
    ideal_term: Mapped[int | None]
    recommended_term: Mapped[int | None]
    credits: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    valid_from: Mapped[date | None]
    valid_until: Mapped[date | None]
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    curriculum_version: Mapped[CurriculumVersion] = relationship(back_populates="subjects")
    subject: Mapped["Subject"] = relationship(back_populates="curriculum_entries")  # noqa: F821


class CurriculumRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_requirements"

    curriculum_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[CurriculumCategory] = mapped_column(
        Enum(CurriculumCategory, native_enum=False, length=32)
    )
    minimum_credits: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    minimum_subjects: Mapped[int | None]
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    curriculum_version: Mapped[CurriculumVersion] = relationship(back_populates="requirements")


from app.models.offerings import SectionCourseOffering, Subject  # noqa: E402
