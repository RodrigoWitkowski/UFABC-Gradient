from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import (
    Course,
    CourseCurriculumSubject,
    CurriculumRequirement,
    CurriculumVersion,
)
from app.models.enums import CurriculumCategorySource
from app.models.offerings import Subject
from app.schemas.curriculum import CurriculumImportRequest
from app.services.normalization.text import normalize_code, normalize_text


class CurriculumService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_curriculum(self, payload: CurriculumImportRequest) -> CurriculumVersion:
        course = self.resolve_or_promote_course(
            code=payload.course.code,
            name=payload.course.name,
            source="curriculum_import",
        )

        curriculum = self.session.scalar(
            select(CurriculumVersion).where(
                CurriculumVersion.course_id == course.id,
                CurriculumVersion.version == payload.version,
            )
        )
        if curriculum is None:
            curriculum = CurriculumVersion(course=course, version=payload.version)
            self.session.add(curriculum)
        curriculum.admission_year_start = payload.admission_year_start
        curriculum.admission_year_end = payload.admission_year_end
        curriculum.valid_from = payload.valid_from
        curriculum.valid_until = payload.valid_until
        curriculum.unlisted_subject_category = payload.unlisted_subject_category
        curriculum.metadata_ = payload.metadata
        self.session.flush()

        if payload.replace_existing:
            curriculum.subjects.clear()
            curriculum.requirements.clear()
            self.session.flush()

        existing_entries = {entry.subject.code: entry for entry in curriculum.subjects}
        for item in payload.subjects:
            subject_code = normalize_code(item.code)
            if subject_code is None:
                raise ValueError("codigo da disciplina ausente")
            subject = self.session.scalar(select(Subject).where(Subject.code == subject_code))
            if subject is None:
                subject = Subject(
                    code=subject_code,
                    name=item.name,
                    normalized_name=normalize_text(item.name),
                )
                self.session.add(subject)
                self.session.flush()
            elif item.name:
                subject.name = item.name
                subject.normalized_name = normalize_text(item.name)

            entry = existing_entries.get(subject_code)
            if entry is None:
                entry = CourseCurriculumSubject(curriculum_version=curriculum, subject=subject)
                self.session.add(entry)
                existing_entries[subject_code] = entry
            entry.category = item.category
            entry.category_source = item.category_source
            entry.ideal_term = item.ideal_term
            entry.recommended_term = item.recommended_term
            entry.credits = item.credits
            entry.valid_from = item.valid_from
            entry.valid_until = item.valid_until
            entry.metadata_ = item.metadata

        if payload.materialize_unlisted_subjects and payload.unlisted_subject_category:
            explicit_subject_ids = {entry.subject.id for entry in curriculum.subjects}
            for subject in self.session.scalars(select(Subject)).all():
                if subject.id in explicit_subject_ids:
                    continue
                curriculum.subjects.append(
                    CourseCurriculumSubject(
                        subject=subject,
                        category=payload.unlisted_subject_category,
                        category_source=CurriculumCategorySource.DERIVED_RULE,
                        metadata_={"derived_rule": "unlisted_subject_default"},
                    )
                )

        if not payload.replace_existing:
            existing_requirements = {item.category: item for item in curriculum.requirements}
        else:
            existing_requirements = {}
        for requirement_input in payload.requirements:
            requirement = existing_requirements.get(requirement_input.category)
            if requirement is None:
                requirement = CurriculumRequirement(
                    curriculum_version=curriculum,
                    category=requirement_input.category,
                )
                self.session.add(requirement)
            requirement.minimum_credits = requirement_input.minimum_credits
            requirement.minimum_subjects = requirement_input.minimum_subjects
            requirement.metadata_ = requirement_input.metadata

        self.session.flush()
        return curriculum

    def resolve_or_promote_course(self, *, code: str, name: str, source: str) -> Course:
        course_code = normalize_code(code)
        if course_code is None:
            raise ValueError("codigo do curso ausente")
        normalized_name = normalize_text(name)
        course = self.session.scalar(select(Course).where(Course.code == course_code))
        if course is None:
            course = self.session.scalar(
                select(Course)
                .where(
                    Course.normalized_name == normalized_name,
                    Course.source == "offer_import",
                    Course.code.like("AUTO-%"),
                )
                .limit(1)
            )
        if course is None:
            course = Course(
                code=course_code,
                name=name,
                normalized_name=normalized_name,
                source=source,
            )
            self.session.add(course)
        else:
            course.code = course_code
            course.name = name
            course.normalized_name = normalized_name
            course.source = source
        self.session.flush()
        return course
