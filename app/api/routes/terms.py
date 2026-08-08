from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.dependencies import DatabaseSession
from app.api.serializers import serialize_section
from app.models.imports import Term
from app.models.offerings import Section, SectionTeacher
from app.schemas.offerings import SectionListRead, TermRead

router = APIRouter(prefix="/terms", tags=["terms"])


@router.get("", response_model=list[TermRead])
def list_terms(db: DatabaseSession) -> list[TermRead]:
    terms = db.scalars(
        select(Term)
        .join(Section, Section.term_id == Term.id)
        .where(Section.is_active.is_(True))
        .distinct()
        .order_by(Term.year.desc(), Term.term_number.desc())
    ).all()
    return [TermRead.model_validate(term, from_attributes=True) for term in terms]


@router.get("/{term_code}/sections", response_model=SectionListRead)
def list_sections(
    term_code: str,
    db: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    active_only: bool = True,
) -> SectionListRead:
    term = db.scalar(select(Term).where(Term.code == term_code))
    if term is None:
        raise HTTPException(status_code=404, detail="quadrimestre nao encontrado")
    filters = [Section.term_id == term.id]
    if active_only:
        filters.append(Section.is_active.is_(True))
    total = db.scalar(select(func.count(Section.id)).where(*filters)) or 0
    sections = db.scalars(
        select(Section)
        .where(*filters)
        .options(
            selectinload(Section.subject),
            selectinload(Section.teachers).selectinload(SectionTeacher.teacher),
            selectinload(Section.meetings),
        )
        .order_by(Section.code)
        .offset(offset)
        .limit(limit)
    ).all()
    return SectionListRead(
        total=total,
        offset=offset,
        limit=limit,
        items=[serialize_section(section) for section in sections],
    )
