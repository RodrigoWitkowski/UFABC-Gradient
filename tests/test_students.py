from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import CourseCurriculumSubject
from app.models.enums import (
    CourseStrategy,
    CurriculumCategory,
    CurriculumCategorySource,
)
from app.models.students import StudentCourse
from app.schemas.curriculum import CurriculumImportRequest
from app.schemas.students import AcademicProfileUpdate, StudentCreate
from app.services.curriculum import CurriculumService
from app.services.students import StudentService


def import_curriculum(
    session: Session,
    *,
    course_code: str,
    course_name: str,
    category: CurriculumCategory,
) -> None:
    payload = CurriculumImportRequest.model_validate(
        {
            "course": {"code": course_code, "name": course_name},
            "version": "2025",
            "admission_year_start": 2025,
            "unlisted_subject_category": "free",
            "subjects": [
                {
                    "code": "MCCC001-23",
                    "name": "ALGORITMOS",
                    "category": category,
                    "ideal_term": 3 if category == CurriculumCategory.MANDATORY else None,
                    "credits": 4,
                }
            ],
        }
    )
    CurriculumService(session).import_curriculum(payload)


def test_student_supports_multiple_courses_and_matrix_suggestion(session: Session) -> None:
    import_curriculum(
        session,
        course_code="BCT",
        course_name="Bacharelado em Ciência e Tecnologia",
        category=CurriculumCategory.LIMITED,
    )
    import_curriculum(
        session,
        course_code="BCC",
        course_name="Bacharelado em Ciência da Computação",
        category=CurriculumCategory.MANDATORY,
    )
    service = StudentService(session)
    student = service.create_student(StudentCreate(admission_year=2025, admission_shift="Noturno"))
    payload = AcademicProfileUpdate.model_validate(
        {
            "admission_year": 2025,
            "admission_shift": "Noturno",
            "campus": "SA",
            "cr": 3.2,
            "ca": 3.4,
            "course_strategy": "weighted_courses",
            "courses": [
                {
                    "course_code": "BCT",
                    "is_primary": False,
                    "weight": 0.4,
                    "cp": 0.72,
                    "ik": 0.68,
                },
                {
                    "course_code": "BCC",
                    "is_primary": True,
                    "weight": 0.6,
                    "cp": 0.38,
                    "ik": 0.41,
                },
            ],
            "completed_subjects": [
                {
                    "code": "BCN0001-15",
                    "name": "BASES COMPUTACIONAIS DA CIÊNCIA",
                    "term": "2025:1",
                    "grade": "A",
                    "credits": 4,
                }
            ],
            "in_progress_subjects": [
                {
                    "code": "MCCC001-23",
                    "term": "2026:3",
                }
            ],
            "preferences": {
                "hard_constraints": {"allowed_campuses": ["SA"]},
                "soft_preferences": {"prefer_night": 1.0},
            },
        }
    )

    service.update_academic_profile(student.id, payload)
    session.commit()
    loaded = service.get_student(student.id)

    assert loaded.course_strategy == CourseStrategy.WEIGHTED_COURSES
    assert loaded.ca == Decimal("3.4000")
    assert len(loaded.courses) == 2
    assert all(item.curriculum_version.version == "2025" for item in loaded.courses)
    assert sum(item.is_primary for item in loaded.courses) == 1
    assert loaded.accumulated_credits == Decimal("4.00")
    assert loaded.completed_subjects[0].grade == "A"
    assert loaded.preferences is not None
    assert loaded.preferences.hard_constraints == {"allowed_campuses": ["SA"]}

    classifications = service.classify_subject(student.id, "MCCC001-23")
    by_course = {item.course_code: item.category for item in classifications.classifications}
    assert by_course == {
        "BCT": CurriculumCategory.LIMITED,
        "BCC": CurriculumCategory.MANDATORY,
    }


def test_unlisted_subject_uses_derived_curriculum_rule(session: Session) -> None:
    import_curriculum(
        session,
        course_code="BCC",
        course_name="Bacharelado em Ciência da Computação",
        category=CurriculumCategory.MANDATORY,
    )
    service = StudentService(session)
    student = service.create_student(StudentCreate(admission_year=2025))
    service.update_academic_profile(
        student.id,
        AcademicProfileUpdate.model_validate(
            {
                "admission_year": 2025,
                "courses": [{"course_code": "BCC", "is_primary": True}],
                "in_progress_subjects": [{"code": "LIVRE001", "name": "DISCIPLINA LIVRE"}],
            }
        ),
    )
    session.commit()

    result = service.classify_subject(student.id, "LIVRE001")

    assert result.classifications[0].category == CurriculumCategory.FREE
    assert result.classifications[0].category_source == CurriculumCategorySource.DERIVED_RULE


def test_weighted_strategy_requires_weights_summing_one() -> None:
    with pytest.raises(ValidationError, match="devem somar 1"):
        AcademicProfileUpdate.model_validate(
            {
                "admission_year": 2025,
                "course_strategy": "weighted_courses",
                "courses": [
                    {"course_code": "BCT", "is_primary": True, "weight": 0.4},
                    {"course_code": "BCC", "weight": 0.4},
                ],
            }
        )


def test_materialized_free_category_is_persisted(session: Session) -> None:
    import_curriculum(
        session,
        course_code="BCC",
        course_name="Bacharelado em Ciência da Computação",
        category=CurriculumCategory.MANDATORY,
    )
    curriculum = CurriculumService(session).import_curriculum(
        CurriculumImportRequest.model_validate(
            {
                "course": {
                    "code": "BCT",
                    "name": "Bacharelado em Ciência e Tecnologia",
                },
                "version": "2025",
                "admission_year_start": 2025,
                "unlisted_subject_category": "free",
                "materialize_unlisted_subjects": True,
                "subjects": [],
            }
        )
    )
    session.commit()

    entries = session.scalars(
        select(CourseCurriculumSubject).where(
            CourseCurriculumSubject.curriculum_version_id == curriculum.id
        )
    ).all()
    assert len(entries) == 1
    assert entries[0].category == CurriculumCategory.FREE
    assert entries[0].category_source == CurriculumCategorySource.DERIVED_RULE


def test_academic_profile_replacement_does_not_duplicate_courses(session: Session) -> None:
    import_curriculum(
        session,
        course_code="BCC",
        course_name="Bacharelado em Ciência da Computação",
        category=CurriculumCategory.MANDATORY,
    )
    service = StudentService(session)
    student = service.create_student(StudentCreate(admission_year=2025))
    payload = AcademicProfileUpdate.model_validate(
        {
            "admission_year": 2025,
            "courses": [{"course_code": "BCC", "is_primary": True}],
        }
    )

    service.update_academic_profile(student.id, payload)
    service.update_academic_profile(student.id, payload)
    session.commit()

    assert len(session.scalars(select(StudentCourse)).all()) == 1
