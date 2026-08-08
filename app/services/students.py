import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.curriculum import Course, CourseCurriculumSubject, CurriculumVersion
from app.models.enums import CurriculumCategorySource
from app.models.imports import Term
from app.models.offerings import Subject
from app.models.students import (
    StudentCompletedSubject,
    StudentCourse,
    StudentInProgressSubject,
    StudentPreference,
    StudentProfile,
)
from app.schemas.students import (
    AcademicProfileUpdate,
    StudentCreate,
    StudentSubjectClassificationsRead,
)
from app.services.credit_limits import calculate_max_quarter_credits
from app.services.normalization.text import (
    clean_text,
    normalize_code,
    normalize_term_code,
    normalize_text,
)


class StudentNotFoundError(ValueError):
    pass


class StudentAcademicDataLockedError(ValueError):
    pass


class StudentService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_student(self, payload: StudentCreate) -> StudentProfile:
        profile = StudentProfile(
            ra=clean_text(payload.ra),
            display_name=clean_text(payload.display_name),
            admission_year=payload.admission_year,
            admission_shift=clean_text(payload.admission_shift),
            campus=clean_text(payload.campus),
            accumulated_credits=Decimal(0),
            preferences=StudentPreference(hard_constraints={}, soft_preferences={}),
        )
        self.session.add(profile)
        self.session.flush()
        return profile

    def get_student(self, student_id: uuid.UUID) -> StudentProfile:
        profile = self.session.scalar(
            select(StudentProfile)
            .where(StudentProfile.id == student_id)
            .options(
                selectinload(StudentProfile.courses).selectinload(StudentCourse.course),
                selectinload(StudentProfile.courses).selectinload(StudentCourse.curriculum_version),
                selectinload(StudentProfile.completed_subjects).selectinload(
                    StudentCompletedSubject.subject
                ),
                selectinload(StudentProfile.completed_subjects).selectinload(
                    StudentCompletedSubject.term
                ),
                selectinload(StudentProfile.in_progress_subjects).selectinload(
                    StudentInProgressSubject.subject
                ),
                selectinload(StudentProfile.in_progress_subjects).selectinload(
                    StudentInProgressSubject.term
                ),
                selectinload(StudentProfile.preferences),
                selectinload(StudentProfile.history_import),
            )
        )
        if profile is None:
            raise StudentNotFoundError("perfil de aluno nao encontrado")
        return profile

    def update_academic_profile(
        self,
        student_id: uuid.UUID,
        payload: AcademicProfileUpdate,
    ) -> StudentProfile:
        profile = self.get_student(student_id)
        if profile.history_import is not None:
            self._ensure_locked_fields_match(profile, payload)
        profile.ra = clean_text(payload.ra)
        profile.admission_year = payload.admission_year
        profile.admission_shift = clean_text(payload.admission_shift)
        profile.campus = clean_text(payload.campus)
        profile.cr = payload.cr
        if profile.history_import is None:
            profile.ca = payload.ca
            profile.max_quarter_credits = calculate_max_quarter_credits(payload.ca)
        profile.course_strategy = payload.course_strategy

        profile.courses.clear()
        profile.completed_subjects.clear()
        profile.in_progress_subjects.clear()
        self.session.flush()

        for course_input in payload.courses:
            course_code = normalize_code(course_input.course_code)
            course = self.session.scalar(select(Course).where(Course.code == course_code))
            if course is None:
                raise ValueError(f"curso nao encontrado: {course_input.course_code}")
            curriculum = self._resolve_curriculum(
                course=course,
                version=course_input.curriculum_version,
                admission_year=payload.admission_year,
            )
            profile.courses.append(
                StudentCourse(
                    course=course,
                    curriculum_version=curriculum,
                    is_primary=course_input.is_primary,
                    weight=course_input.weight,
                    cp=course_input.cp,
                    ik=course_input.ik,
                )
            )

        completed_credits = Decimal(0)
        for completed_input in payload.completed_subjects:
            subject = self._resolve_subject(completed_input.code, completed_input.name)
            term = self._resolve_term(completed_input.term)
            completed_credits += completed_input.credits or Decimal(0)
            grade = clean_text(completed_input.grade)
            profile.completed_subjects.append(
                StudentCompletedSubject(
                    subject=subject,
                    term=term,
                    grade=grade.upper() if grade else None,
                    credits=completed_input.credits,
                    metadata_=completed_input.metadata,
                )
            )

        for progress_input in payload.in_progress_subjects:
            subject = self._resolve_subject(progress_input.code, progress_input.name)
            profile.in_progress_subjects.append(
                StudentInProgressSubject(
                    subject=subject,
                    term=self._resolve_term(progress_input.term),
                )
            )

        profile.accumulated_credits = (
            payload.accumulated_credits
            if payload.accumulated_credits is not None
            else completed_credits
        )
        if profile.preferences is None:
            profile.preferences = StudentPreference()
        profile.preferences.hard_constraints = payload.preferences.hard_constraints
        profile.preferences.soft_preferences = payload.preferences.soft_preferences
        self.session.flush()
        return profile

    def _ensure_locked_fields_match(
        self,
        profile: StudentProfile,
        payload: AcademicProfileUpdate,
    ) -> None:
        if clean_text(payload.ra) != profile.ra:
            raise StudentAcademicDataLockedError(
                "RA veio do historico importado e nao pode ser editado manualmente"
            )
        if payload.admission_year != profile.admission_year:
            raise StudentAcademicDataLockedError(
                "ano de ingresso veio do historico importado e nao pode ser editado manualmente"
            )
        if clean_text(payload.admission_shift) != profile.admission_shift:
            raise StudentAcademicDataLockedError(
                "turno veio do historico importado e nao pode ser editado manualmente"
            )
        if clean_text(payload.campus) != profile.campus:
            raise StudentAcademicDataLockedError(
                "campus veio do historico importado e nao pode ser editado manualmente"
            )
        if payload.cr != profile.cr:
            raise StudentAcademicDataLockedError(
                "CR veio do historico importado e nao pode ser editado manualmente"
            )
        if payload.ca != profile.ca:
            raise StudentAcademicDataLockedError(
                "CA veio do historico importado e nao pode ser editado manualmente"
            )
        if payload.accumulated_credits != profile.accumulated_credits:
            raise StudentAcademicDataLockedError(
                "creditos acumulados vieram do historico importado "
                "e nao podem ser editados manualmente"
            )
        if self._course_payload_snapshot(payload) != self._course_profile_snapshot(profile):
            raise StudentAcademicDataLockedError(
                "cursos, matriz, CP e IK vieram do historico importado "
                "e nao podem ser editados manualmente"
            )
        if (
            self._completed_payload_snapshot(payload)
            != self._completed_profile_snapshot(profile)
        ):
            raise StudentAcademicDataLockedError(
                "disciplinas concluidas vieram do historico importado "
                "e nao podem ser editadas manualmente"
            )
        if (
            self._in_progress_payload_snapshot(payload)
            != self._in_progress_profile_snapshot(profile)
        ):
            raise StudentAcademicDataLockedError(
                "disciplinas em andamento vieram do historico importado "
                "e nao podem ser editadas manualmente"
            )

    @staticmethod
    def _course_payload_snapshot(
        payload: AcademicProfileUpdate,
    ) -> list[tuple[str, str | None, bool, Decimal | None, Decimal | None, Decimal | None]]:
        return sorted(
            (
                normalize_code(item.course_code),
                clean_text(item.curriculum_version),
                item.is_primary,
                item.weight,
                item.cp,
                item.ik,
            )
            for item in payload.courses
        )

    @staticmethod
    def _course_profile_snapshot(
        profile: StudentProfile,
    ) -> list[tuple[str, str | None, bool, Decimal | None, Decimal | None, Decimal | None]]:
        return sorted(
            (
                item.course.code,
                item.curriculum_version.version,
                item.is_primary,
                item.weight,
                item.cp,
                item.ik,
            )
            for item in profile.courses
        )

    @staticmethod
    def _completed_payload_snapshot(
        payload: AcademicProfileUpdate,
    ) -> list[tuple[str, str | None, str | None, Decimal | None]]:
        return sorted(
            (
                normalize_code(item.code),
                clean_text(item.term),
                clean_text(item.grade).upper() if clean_text(item.grade) else None,
                item.credits,
            )
            for item in payload.completed_subjects
        )

    @staticmethod
    def _completed_profile_snapshot(
        profile: StudentProfile,
    ) -> list[tuple[str, str | None, str | None, Decimal | None]]:
        return sorted(
            (
                item.subject.code,
                item.term.code if item.term else None,
                item.grade,
                item.credits,
            )
            for item in profile.completed_subjects
        )

    @staticmethod
    def _in_progress_payload_snapshot(
        payload: AcademicProfileUpdate,
    ) -> list[tuple[str, str | None]]:
        return sorted(
            (normalize_code(item.code), clean_text(item.term))
            for item in payload.in_progress_subjects
        )

    @staticmethod
    def _in_progress_profile_snapshot(
        profile: StudentProfile,
    ) -> list[tuple[str, str | None]]:
        return sorted(
            (
                item.subject.code,
                item.term.code if item.term else None,
            )
            for item in profile.in_progress_subjects
        )

    def classify_subject(
        self,
        student_id: uuid.UUID,
        subject_code: str,
    ) -> StudentSubjectClassificationsRead:
        profile = self.get_student(student_id)
        normalized_code = normalize_code(subject_code)
        subject = self.session.scalar(select(Subject).where(Subject.code == normalized_code))
        if subject is None:
            raise ValueError(f"disciplina nao encontrada: {subject_code}")

        classifications = []
        for student_course in profile.courses:
            entry = self.session.scalar(
                select(CourseCurriculumSubject).where(
                    CourseCurriculumSubject.curriculum_version_id
                    == student_course.curriculum_version_id,
                    CourseCurriculumSubject.subject_id == subject.id,
                )
            )
            if entry is not None:
                category = entry.category
                category_source = entry.category_source
                ideal_term = entry.ideal_term
                credits = entry.credits
                explanation = (
                    f"Classificacao {category.value} na matriz "
                    f"{student_course.curriculum_version.version} de "
                    f"{student_course.course.code}."
                )
            elif student_course.curriculum_version.unlisted_subject_category is not None:
                category = student_course.curriculum_version.unlisted_subject_category
                category_source = CurriculumCategorySource.DERIVED_RULE
                ideal_term = None
                credits = None
                explanation = (
                    f"Classificacao {category.value} derivada da regra para disciplinas "
                    f"nao listadas na matriz de {student_course.course.code}."
                )
            else:
                category = None
                category_source = None
                ideal_term = None
                credits = None
                explanation = (
                    f"A matriz {student_course.curriculum_version.version} de "
                    f"{student_course.course.code} nao possui classificacao para a disciplina."
                )
            classifications.append(
                {
                    "course_id": student_course.course.id,
                    "course_code": student_course.course.code,
                    "course_name": student_course.course.name,
                    "curriculum_version_id": student_course.curriculum_version.id,
                    "curriculum_version": student_course.curriculum_version.version,
                    "category": category,
                    "category_source": category_source,
                    "ideal_term": ideal_term,
                    "credits": credits,
                    "explanation": explanation,
                }
            )

        return StudentSubjectClassificationsRead.model_validate(
            {
                "student_id": profile.id,
                "subject_id": subject.id,
                "subject_code": subject.code,
                "subject_name": subject.name,
                "classifications": classifications,
            }
        )

    def _resolve_curriculum(
        self,
        *,
        course: Course,
        version: str | None,
        admission_year: int,
    ) -> CurriculumVersion:
        if version:
            curriculum = self.session.scalar(
                select(CurriculumVersion).where(
                    CurriculumVersion.course_id == course.id,
                    CurriculumVersion.version == version,
                )
            )
            if curriculum is None:
                raise ValueError(f"matriz {version} nao encontrada para o curso {course.code}")
            return curriculum

        curriculum = self.session.scalar(
            select(CurriculumVersion)
            .where(
                CurriculumVersion.course_id == course.id,
                or_(
                    CurriculumVersion.admission_year_start.is_(None),
                    CurriculumVersion.admission_year_start <= admission_year,
                ),
                or_(
                    CurriculumVersion.admission_year_end.is_(None),
                    CurriculumVersion.admission_year_end >= admission_year,
                ),
            )
            .order_by(
                func.coalesce(CurriculumVersion.admission_year_start, 0).desc(),
                CurriculumVersion.version.desc(),
            )
            .limit(1)
        )
        if curriculum is None:
            raise ValueError(
                f"nenhuma matriz de {course.code} atende ao ano de ingresso {admission_year}"
            )
        return curriculum

    def _resolve_subject(self, code: str, name: str | None) -> Subject:
        subject_code = normalize_code(code)
        subject = self.session.scalar(select(Subject).where(Subject.code == subject_code))
        if subject is not None:
            return subject
        subject_name = clean_text(name)
        if subject_code is None or subject_name is None:
            raise ValueError(f"disciplina nao encontrada e nome nao informado: {code}")
        subject = Subject(
            code=subject_code,
            name=subject_name,
            normalized_name=normalize_text(subject_name),
        )
        self.session.add(subject)
        self.session.flush()
        return subject

    def _resolve_term(self, code: str | None) -> Term | None:
        if code is None:
            return None
        term_code = normalize_term_code(code)
        term = self.session.scalar(select(Term).where(Term.code == term_code))
        if term is None:
            year, number = term_code.split(":")
            term = Term(code=term_code, year=int(year), term_number=int(number))
            self.session.add(term)
            self.session.flush()
        return term
