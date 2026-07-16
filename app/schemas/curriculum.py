import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import CurriculumCategory, CurriculumCategorySource


class CourseInput(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=512)


class CourseCreate(CourseInput):
    pass


class CourseRead(CourseInput):
    id: uuid.UUID
    source: str


class CurriculumVersionSummaryRead(BaseModel):
    id: uuid.UUID
    version: str
    admission_year_start: int | None
    admission_year_end: int | None
    unlisted_subject_category: CurriculumCategory | None


class CourseWithCurriculaRead(CourseRead):
    curriculum_versions: list[CurriculumVersionSummaryRead]


class CurriculumSubjectInput(BaseModel):
    code: str
    name: str
    category: CurriculumCategory
    category_source: CurriculumCategorySource = CurriculumCategorySource.EXPLICIT
    ideal_term: int | None = Field(default=None, ge=1)
    recommended_term: int | None = Field(default=None, ge=1)
    credits: Decimal | None = Field(default=None, ge=0)
    valid_from: date | None = None
    valid_until: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurriculumRequirementInput(BaseModel):
    category: CurriculumCategory
    minimum_credits: Decimal | None = Field(default=None, ge=0)
    minimum_subjects: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurriculumImportRequest(BaseModel):
    course: CourseInput
    version: str = Field(min_length=1, max_length=64)
    admission_year_start: int | None = Field(default=None, ge=2006)
    admission_year_end: int | None = Field(default=None, ge=2006)
    valid_from: date | None = None
    valid_until: date | None = None
    unlisted_subject_category: CurriculumCategory | None = None
    materialize_unlisted_subjects: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    subjects: list[CurriculumSubjectInput]
    requirements: list[CurriculumRequirementInput] = Field(default_factory=list)
    replace_existing: bool = False


class CurriculumSubjectRead(BaseModel):
    subject_id: uuid.UUID
    code: str
    name: str
    category: CurriculumCategory
    category_source: CurriculumCategorySource
    ideal_term: int | None
    recommended_term: int | None
    credits: Decimal | None
    metadata: dict[str, Any]


class CurriculumRequirementRead(BaseModel):
    category: CurriculumCategory
    minimum_credits: Decimal | None
    minimum_subjects: int | None
    metadata: dict[str, Any]


class CurriculumRead(BaseModel):
    id: uuid.UUID
    course: CourseRead
    version: str
    admission_year_start: int | None
    admission_year_end: int | None
    valid_from: date | None
    valid_until: date | None
    unlisted_subject_category: CurriculumCategory | None
    metadata: dict[str, Any]
    subjects: list[CurriculumSubjectRead]
    requirements: list[CurriculumRequirementRead]
