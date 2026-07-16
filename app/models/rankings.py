import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Ranking(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rankings"
    __table_args__ = (
        Index("ix_rankings_student_term_computed", "student_profile_id", "term_id", "computed_at"),
    )

    term_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("terms.id", ondelete="RESTRICT"), index=True
    )
    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), index=True
    )
    source_ranking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rankings.id", ondelete="SET NULL"), index=True
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_limit: Mapped[int] = mapped_column(Integer)
    candidate_count: Mapped[int] = mapped_column(Integer)
    item_count: Mapped[int] = mapped_column(Integer)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    term: Mapped["Term"] = relationship()  # noqa: F821
    student_profile: Mapped["StudentProfile"] = relationship()  # noqa: F821
    items: Mapped[list["RankingItem"]] = relationship(
        back_populates="ranking",
        cascade="all, delete-orphan",
        order_by="RankingItem.position",
    )


class RankingItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ranking_items"
    __table_args__ = (
        UniqueConstraint("ranking_id", "section_id", name="uq_ranking_item_section"),
        UniqueConstraint("ranking_id", "position", name="uq_ranking_item_position"),
        Index("ix_ranking_items_ranking_score", "ranking_id", "total_score"),
    )

    ranking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rankings.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    total_score: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    score_breakdown: Mapped[dict[str, float]] = mapped_column(JSON)
    section_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    curriculum_classifications: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    teacher_statistics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    seat_probability: Mapped[dict[str, Any]] = mapped_column(JSON)
    explanations: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)

    ranking: Mapped[Ranking] = relationship(back_populates="items")
    section: Mapped["Section"] = relationship()  # noqa: F821


from app.models.imports import Term  # noqa: E402
from app.models.offerings import Section  # noqa: E402
from app.models.students import StudentProfile  # noqa: E402
