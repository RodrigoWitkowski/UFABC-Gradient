from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.curriculum import Course, CourseCurriculumSubject, CurriculumVersion
from app.models.enums import CurriculumCategory, CurriculumCategorySource
from app.schemas.curriculum import CurriculumImportRequest
from app.services.official_curricula import (
    import_official_curricula,
    load_official_curricula,
)

EXPECTED_COUNTS = {
    ("BCT", "2015"): {CurriculumCategory.MANDATORY: 26, CurriculumCategory.LIMITED: 291},
    ("BCT", "2023"): {CurriculumCategory.MANDATORY: 24, CurriculumCategory.LIMITED: 306},
    ("BCH", "2022"): {CurriculumCategory.MANDATORY: 22, CurriculumCategory.LIMITED: 270},
    ("BCC", "2023"): {CurriculumCategory.MANDATORY: 51, CurriculumCategory.LIMITED: 73},
}


def payloads_by_version() -> dict[tuple[str, str], CurriculumImportRequest]:
    return {
        (payload.course.code, payload.version): payload for payload in load_official_curricula()
    }


def category_for(payload: CurriculumImportRequest, subject_code: str) -> CurriculumCategory | None:
    for subject in payload.subjects:
        if subject.code == subject_code:
            return subject.category
    return payload.unlisted_subject_category


def test_official_curriculum_files_have_expected_classifications() -> None:
    payloads = payloads_by_version()

    assert set(payloads) == set(EXPECTED_COUNTS)
    for key, expected in EXPECTED_COUNTS.items():
        payload = payloads[key]
        actual = {
            category: sum(subject.category == category for subject in payload.subjects)
            for category in expected
        }
        assert actual == expected
        assert payload.unlisted_subject_category == CurriculumCategory.FREE
        assert payload.requirements == []
        assert all(
            subject.category_source == CurriculumCategorySource.EXPLICIT
            for subject in payload.subjects
        )

    assert category_for(payloads[("BCT", "2023")], "MCCC001-23") == CurriculumCategory.LIMITED
    assert category_for(payloads[("BCC", "2023")], "MCCC001-23") == CurriculumCategory.MANDATORY
    assert category_for(payloads[("BCH", "2022")], "BHQ0004-19") == CurriculumCategory.MANDATORY
    assert category_for(payloads[("BCT", "2023")], "BHQ0004-19") == CurriculumCategory.LIMITED
    assert category_for(payloads[("BCT", "2015")], "BIJ0207-15") == CurriculumCategory.MANDATORY
    assert category_for(payloads[("BCT", "2023")], "BIJ0207-15") == CurriculumCategory.LIMITED
    assert category_for(payloads[("BCT", "2023")], "SUBJECT-NOT-LISTED") == CurriculumCategory.FREE


def test_official_curriculum_import_is_idempotent(session: Session) -> None:
    expected_entries = sum(sum(counts.values()) for counts in EXPECTED_COUNTS.values())

    first_results = import_official_curricula(session)
    session.commit()
    second_results = import_official_curricula(session)
    session.commit()

    assert [(item.course_code, item.version) for item in first_results] == [
        (item.course_code, item.version) for item in second_results
    ]
    assert session.scalar(select(func.count()).select_from(Course)) == 3
    assert session.scalar(select(func.count()).select_from(CurriculumVersion)) == 4
    imported_entries = session.scalar(
        select(func.count()).select_from(CourseCurriculumSubject)
    )
    assert imported_entries == expected_entries
