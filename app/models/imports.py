import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ImportIssueLevel, ImportStatus


class Term(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "terms"

    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    year: Mapped[int]
    term_number: Mapped[int]

    import_batches: Mapped[list["ImportBatch"]] = relationship(back_populates="term")
    sections: Mapped[list["Section"]] = relationship(back_populates="term")  # noqa: F821


class ImportFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_files"
    __table_args__ = (
        UniqueConstraint("sha256", "original_filename", name="uq_import_file_hash_name"),
    )

    original_filename: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str | None] = mapped_column(String(255))

    batches: Mapped[list["ImportBatch"]] = relationship(back_populates="import_file")


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_batches"

    import_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_files.id", ondelete="RESTRICT"), index=True
    )
    term_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("terms.id", ondelete="RESTRICT"), index=True
    )
    comparison_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, native_enum=False, length=40), default=ImportStatus.PENDING
    )
    source_sheet: Mapped[str | None] = mapped_column(String(255))
    parser_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    total_rows: Mapped[int] = mapped_column(default=0)
    imported_rows: Mapped[int] = mapped_column(default=0)
    invalid_rows: Mapped[int] = mapped_column(default=0)
    warning_count: Mapped[int] = mapped_column(default=0)
    added_sections: Mapped[int] = mapped_column(default=0)
    changed_sections: Mapped[int] = mapped_column(default=0)
    removed_sections: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    import_file: Mapped[ImportFile] = relationship(back_populates="batches")
    term: Mapped[Term | None] = relationship(back_populates="import_batches")
    issues: Mapped[list["ImportIssue"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class ImportIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_errors"
    __table_args__ = (Index("ix_import_errors_batch_level", "import_batch_id", "level"),)

    import_batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[ImportIssueLevel] = mapped_column(
        Enum(ImportIssueLevel, native_enum=False, length=16)
    )
    code: Mapped[str] = mapped_column(String(100))
    row_number: Mapped[int | None]
    field: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    batch: Mapped[ImportBatch] = relationship(back_populates="issues")


from app.models.offerings import Section  # noqa: E402
