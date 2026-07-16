import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import DatabaseSession
from app.api.serializers import serialize_curriculum
from app.models.curriculum import Course, CourseCurriculumSubject, CurriculumVersion
from app.schemas.curriculum import (
    CourseCreate,
    CourseRead,
    CourseWithCurriculaRead,
    CurriculumImportRequest,
    CurriculumRead,
    CurriculumVersionSummaryRead,
)
from app.services.curriculum import CurriculumService
from app.services.normalization.text import normalize_code

router = APIRouter(tags=["curricula"])


def serialize_curriculum_summary(
    curriculum: CurriculumVersion,
) -> CurriculumVersionSummaryRead:
    return CurriculumVersionSummaryRead(
        id=curriculum.id,
        version=curriculum.version,
        admission_year_start=curriculum.admission_year_start,
        admission_year_end=curriculum.admission_year_end,
        unlisted_subject_category=curriculum.unlisted_subject_category,
    )


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: DatabaseSession) -> CourseRead:
    code = normalize_code(payload.code)
    if code is None:
        raise HTTPException(status_code=422, detail="codigo do curso ausente")
    if db.scalar(select(Course.id).where(Course.code == code)):
        raise HTTPException(status_code=409, detail="codigo de curso ja cadastrado")
    course = CurriculumService(db).resolve_or_promote_course(
        code=code,
        name=payload.name,
        source="manual",
    )
    db.commit()
    db.refresh(course)
    return CourseRead(id=course.id, code=course.code, name=course.name, source=course.source)


@router.get("/courses", response_model=list[CourseWithCurriculaRead])
def list_courses(db: DatabaseSession) -> list[CourseWithCurriculaRead]:
    courses = db.scalars(
        select(Course)
        .options(selectinload(Course.curriculum_versions))
        .order_by(Course.name, Course.code)
    ).all()
    return [
        CourseWithCurriculaRead(
            id=course.id,
            code=course.code,
            name=course.name,
            source=course.source,
            curriculum_versions=[
                serialize_curriculum_summary(curriculum)
                for curriculum in sorted(
                    course.curriculum_versions,
                    key=lambda item: item.version,
                    reverse=True,
                )
            ],
        )
        for course in courses
    ]


@router.get(
    "/courses/{course_id}/curriculums",
    response_model=list[CurriculumVersionSummaryRead],
)
def list_curriculums(
    course_id: uuid.UUID,
    db: DatabaseSession,
) -> list[CurriculumVersionSummaryRead]:
    course = db.scalar(
        select(Course)
        .where(Course.id == course_id)
        .options(selectinload(Course.curriculum_versions))
    )
    if course is None:
        raise HTTPException(status_code=404, detail="curso nao encontrado")
    return [
        serialize_curriculum_summary(curriculum)
        for curriculum in sorted(
            course.curriculum_versions,
            key=lambda item: item.version,
            reverse=True,
        )
    ]


@router.post("/curriculums/import", response_model=CurriculumRead)
def import_curriculum(
    payload: CurriculumImportRequest,
    db: DatabaseSession,
) -> CurriculumRead:
    try:
        curriculum = CurriculumService(db).import_curriculum(payload)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_curriculum(curriculum)


@router.get(
    "/courses/{course_id}/curriculums/{version}",
    response_model=CurriculumRead,
)
def get_curriculum(
    course_id: uuid.UUID,
    version: str,
    db: DatabaseSession,
) -> CurriculumRead:
    curriculum = db.scalar(
        select(CurriculumVersion)
        .where(
            CurriculumVersion.course_id == course_id,
            CurriculumVersion.version == version,
        )
        .options(
            selectinload(CurriculumVersion.course),
            selectinload(CurriculumVersion.subjects).selectinload(CourseCurriculumSubject.subject),
            selectinload(CurriculumVersion.requirements),
        )
    )
    if curriculum is None:
        raise HTTPException(status_code=404, detail="matriz curricular nao encontrada")
    return serialize_curriculum(curriculum)
