import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    CourseStrategy,
    CurriculumCategory,
    CurriculumCategorySource,
)


class StudentCreate(BaseModel):
    ra: str | None = Field(default=None, pattern=r"^\d{8,16}$")
    display_name: str | None = Field(default=None, max_length=255)
    admission_year: int = Field(ge=2006, le=2100)
    admission_shift: str | None = Field(default=None, max_length=32)
    campus: str | None = Field(default=None, max_length=32)


class StudentCourseInput(BaseModel):
    course_code: str = Field(min_length=1, max_length=64)
    curriculum_version: str | None = Field(default=None, max_length=64)
    is_primary: bool = False
    weight: Decimal | None = Field(default=None, ge=0, le=1)
    cp: Decimal | None = Field(default=None, ge=0, le=1)


class StudentSubjectInput(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=512)
    term: str | None = Field(default=None, max_length=16)


class CompletedSubjectInput(StudentSubjectInput):
    grade: str | None = Field(default=None, max_length=8)
    credits: Decimal | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudentPreferencesInput(BaseModel):
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: dict[str, Any] = Field(default_factory=dict)


class AcademicProfileUpdate(BaseModel):
    ra: str | None = Field(default=None, pattern=r"^\d{8,16}$")
    admission_year: int = Field(ge=2006, le=2100)
    admission_shift: str | None = Field(default=None, max_length=32)
    campus: str | None = Field(default=None, max_length=32)
    cr: Decimal | None = Field(default=None, ge=0, le=4)
    ca: Decimal | None = Field(default=None, ge=0, le=4)
    accumulated_credits: Decimal | None = Field(default=None, ge=0)
    course_strategy: CourseStrategy = CourseStrategy.PRIMARY_COURSE
    courses: list[StudentCourseInput] = Field(min_length=1)
    completed_subjects: list[CompletedSubjectInput] = Field(default_factory=list)
    in_progress_subjects: list[StudentSubjectInput] = Field(default_factory=list)
    preferences: StudentPreferencesInput = Field(default_factory=StudentPreferencesInput)

    @model_validator(mode="after")
    def validate_academic_profile(self) -> "AcademicProfileUpdate":
        course_codes = [item.course_code.strip().casefold() for item in self.courses]
        if len(course_codes) != len(set(course_codes)):
            raise ValueError("cada curso deve aparecer apenas uma vez")
        if sum(item.is_primary for item in self.courses) != 1:
            raise ValueError("informe exatamente um curso principal")
        if self.course_strategy == CourseStrategy.WEIGHTED_COURSES:
            weights = [item.weight for item in self.courses]
            if any(weight is None for weight in weights):
                raise ValueError("todos os cursos precisam de peso na estrategia weighted_courses")
            total = sum((weight or Decimal(0) for weight in weights), start=Decimal(0))
            if abs(total - Decimal(1)) > Decimal("0.000001"):
                raise ValueError("os pesos dos cursos devem somar 1")

        completed = {item.code.strip().casefold() for item in self.completed_subjects}
        in_progress = {item.code.strip().casefold() for item in self.in_progress_subjects}
        if len(completed) != len(self.completed_subjects):
            raise ValueError("disciplinas concluidas nao podem ser repetidas")
        if len(in_progress) != len(self.in_progress_subjects):
            raise ValueError("disciplinas em andamento nao podem ser repetidas")
        overlap = completed & in_progress
        if overlap:
            raise ValueError("uma disciplina nao pode estar concluida e em andamento")
        return self


class StudentCourseRead(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    course_code: str
    course_name: str
    curriculum_version_id: uuid.UUID
    curriculum_version: str
    is_primary: bool
    weight: Decimal | None
    cp: Decimal | None


class StudentSubjectRead(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    code: str
    name: str
    term: str | None


class CompletedSubjectRead(StudentSubjectRead):
    grade: str | None
    credits: Decimal | None
    metadata: dict[str, Any]


class StudentPreferencesRead(BaseModel):
    hard_constraints: dict[str, Any]
    soft_preferences: dict[str, Any]


class StudentRead(BaseModel):
    id: uuid.UUID
    ra: str | None
    display_name: str | None
    admission_year: int
    admission_shift: str | None
    campus: str | None
    cr: Decimal | None
    ca: Decimal | None
    max_quarter_credits: Decimal | None
    accumulated_credits: Decimal
    course_strategy: CourseStrategy
    courses: list[StudentCourseRead]
    completed_subjects: list[CompletedSubjectRead]
    in_progress_subjects: list[StudentSubjectRead]
    preferences: StudentPreferencesRead


class StudentHistoryImportRead(BaseModel):
    student: StudentRead
    original_filename: str
    sha256: str
    issued_at: datetime | None
    imported_at: datetime
    replaced_existing: bool
    completed_count: int
    completed_attempt_count: int
    in_progress_count: int
    ignored_attempt_count: int
    warnings: list[str]


class StudentSubjectClassificationRead(BaseModel):
    course_id: uuid.UUID
    course_code: str
    course_name: str
    curriculum_version_id: uuid.UUID
    curriculum_version: str
    category: CurriculumCategory | None
    category_source: CurriculumCategorySource | None
    ideal_term: int | None
    credits: Decimal | None
    explanation: str


class StudentSubjectClassificationsRead(BaseModel):
    student_id: uuid.UUID
    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    classifications: list[StudentSubjectClassificationRead]
