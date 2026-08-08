import uuid
from datetime import time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    MeetingFrequency,
    MeetingType,
    TeacherAliasStatus,
    TeacherRole,
)


class Subject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subjects"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512))
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)

    sections: Mapped[list["Section"]] = relationship(back_populates="subject")
    curriculum_entries: Mapped[list["CourseCurriculumSubject"]] = relationship(  # noqa: F821
        back_populates="subject"
    )


class Teacher(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teachers"

    canonical_name: Mapped[str] = mapped_column(String(512))
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)

    aliases: Mapped[list["TeacherAlias"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )
    external_identifiers: Mapped[list["ExternalTeacherIdentifier"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )
    sections: Mapped[list["SectionTeacher"]] = relationship(back_populates="teacher")


class TeacherAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teacher_aliases"
    __table_args__ = (
        UniqueConstraint("teacher_id", "normalized_name", name="uq_teacher_alias_teacher_name"),
        Index("ix_teacher_aliases_normalized_status", "normalized_name", "status"),
    )

    teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(512))
    normalized_name: Mapped[str] = mapped_column(String(512))
    status: Mapped[TeacherAliasStatus] = mapped_column(
        Enum(TeacherAliasStatus, native_enum=False, length=32),
        default=TeacherAliasStatus.MATCHED,
    )
    source: Mapped[str] = mapped_column(String(64), default="offer_import")

    teacher: Mapped[Teacher | None] = relationship(back_populates="aliases")


class ExternalTeacherIdentifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "external_teacher_identifiers"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_teacher_external_provider_id"),
    )

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(255))

    teacher: Mapped[Teacher] = relationship(back_populates="external_identifiers")


class Section(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("term_id", "code", name="uq_section_term_code"),
        Index("ix_sections_term_subject", "term_id", "subject_id"),
        Index("ix_sections_term_active", "term_id", "is_active"),
    )

    term_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("terms.id", ondelete="RESTRICT"), index=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), index=True
    )
    first_seen_batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT")
    )
    last_seen_batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(64), index=True)
    class_group: Mapped[str | None] = mapped_column(String(32))
    display_name: Mapped[str | None] = mapped_column(String(768))
    campus: Mapped[str | None] = mapped_column(String(32), index=True)
    shift: Mapped[str | None] = mapped_column(String(32), index=True)
    total_seats: Mapped[int | None]
    reserved_seats: Mapped[int | None]
    workload_code: Mapped[str | None] = mapped_column(String(32))
    theory_hours: Mapped[int | None]
    practice_hours: Mapped[int | None]
    individual_hours: Mapped[int | None]
    extension_hours: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    term: Mapped["Term"] = relationship(back_populates="sections")  # noqa: F821
    subject: Mapped[Subject] = relationship(back_populates="sections")
    teachers: Mapped[list["SectionTeacher"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )
    meetings: Mapped[list["SectionMeeting"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )
    course_links: Mapped[list["SectionCourseOffering"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["SectionRevision"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class SectionTeacher(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "section_teachers"
    __table_args__ = (
        UniqueConstraint("section_id", "role", "position", name="uq_section_teacher_role_position"),
        Index("ix_section_teachers_teacher_role", "teacher_id", "role"),
    )

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teachers.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[TeacherRole] = mapped_column(Enum(TeacherRole, native_enum=False, length=16))
    position: Mapped[int] = mapped_column(SmallInteger)

    section: Mapped[Section] = relationship(back_populates="teachers")
    teacher: Mapped[Teacher] = relationship(back_populates="sections")


class SectionMeeting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "section_meetings"
    __table_args__ = (Index("ix_section_meetings_weekday_time", "weekday", "start_time"),)

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time]
    end_time: Mapped[time]
    campus: Mapped[str | None] = mapped_column(String(32))
    classroom: Mapped[str | None] = mapped_column(String(255))
    frequency: Mapped[MeetingFrequency] = mapped_column(
        Enum(MeetingFrequency, native_enum=False, length=32)
    )
    meeting_type: Mapped[MeetingType] = mapped_column(
        Enum(MeetingType, native_enum=False, length=16)
    )

    section: Mapped[Section] = relationship(back_populates="meetings")


class SectionRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "section_revisions"
    __table_args__ = (
        UniqueConstraint("section_id", "import_batch_id", name="uq_section_revision_batch"),
        Index("ix_section_revisions_section_created", "section_id", "created_at"),
    )

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )
    import_batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, default=list)

    section: Mapped[Section] = relationship(back_populates="revisions")


class SectionCourseOffering(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "section_course_offerings"
    __table_args__ = (
        UniqueConstraint("section_id", "course_id", name="uq_section_course_offering"),
    )

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    reserved_seats: Mapped[int | None]

    section: Mapped[Section] = relationship(back_populates="course_links")
    course: Mapped["Course"] = relationship(back_populates="section_offerings")  # noqa: F821


from app.models.curriculum import Course, CourseCurriculumSubject  # noqa: E402
from app.models.imports import Term  # noqa: E402
