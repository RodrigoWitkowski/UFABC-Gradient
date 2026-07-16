from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import Course, CourseCurriculumSubject
from app.models.enums import CurriculumCategory, CurriculumCategorySource
from app.schemas.curriculum import CurriculumImportRequest
from app.services.curriculum import CurriculumService
from app.services.normalization.text import normalize_text


def curriculum_payload(
    course_code: str,
    course_name: str,
    category: CurriculumCategory,
) -> CurriculumImportRequest:
    return CurriculumImportRequest.model_validate(
        {
            "course": {"code": course_code, "name": course_name},
            "version": "2025",
            "admission_year_start": 2025,
            "subjects": [
                {
                    "code": "MCCC001-23",
                    "name": "ALGORITMOS",
                    "category": category,
                    "category_source": CurriculumCategorySource.EXPLICIT,
                    "ideal_term": 3 if category == CurriculumCategory.MANDATORY else None,
                    "credits": 4,
                }
            ],
        }
    )


def test_same_subject_has_independent_classification_per_course(session: Session) -> None:
    service = CurriculumService(session)
    bct = service.import_curriculum(
        curriculum_payload("BCT", "Bacharelado em Ciência e Tecnologia", CurriculumCategory.LIMITED)
    )
    bcc = service.import_curriculum(
        curriculum_payload(
            "BCC", "Bacharelado em Ciência da Computação", CurriculumCategory.MANDATORY
        )
    )
    session.commit()

    entries = session.scalars(select(CourseCurriculumSubject)).all()
    assert len(entries) == 2
    assert entries[0].subject_id == entries[1].subject_id
    by_course = {entry.curriculum_version.course.code: entry.category for entry in entries}
    assert by_course == {
        "BCT": CurriculumCategory.LIMITED,
        "BCC": CurriculumCategory.MANDATORY,
    }
    assert bct.id != bcc.id


def test_derived_free_category_is_explicitly_recorded(session: Session) -> None:
    payload = curriculum_payload(
        "BCT",
        "Bacharelado em Ciência e Tecnologia",
        CurriculumCategory.FREE,
    )
    payload.subjects[0].category_source = CurriculumCategorySource.DERIVED_RULE

    curriculum = CurriculumService(session).import_curriculum(payload)
    session.commit()

    assert curriculum.subjects[0].category == CurriculumCategory.FREE
    assert curriculum.subjects[0].category_source == CurriculumCategorySource.DERIVED_RULE


def test_curriculum_promotes_course_created_from_offer_instead_of_duplicating(
    session: Session,
) -> None:
    imported_course = Course(
        code="AUTO-1234567890",
        name="BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO",
        normalized_name=normalize_text("BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO"),
        source="offer_import",
    )
    session.add(imported_course)
    session.flush()

    curriculum = CurriculumService(session).import_curriculum(
        curriculum_payload(
            "BCC",
            "Bacharelado em Ciência da Computação",
            CurriculumCategory.MANDATORY,
        )
    )
    session.commit()

    assert curriculum.course.id == imported_course.id
    assert curriculum.course.code == "BCC"
    assert len(session.scalars(select(Course)).all()) == 1
