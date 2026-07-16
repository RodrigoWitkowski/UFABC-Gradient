import uuid
from datetime import datetime, time
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from app.models.enums import (
    CourseStrategy,
    CurriculumCategory,
    CurriculumCategorySource,
    TeacherRole,
    TeacherScoreMetric,
    TeacherStatisticsMode,
)
from app.schemas.offerings import SectionRead
from app.schemas.statistics import TeacherStatisticsEvaluationRead


def _default_grade_weights() -> dict[str, float]:
    return {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0, "O": 0.0}


WEEKDAY_NAMES = {
    "monday": 0,
    "segunda": 0,
    "segunda-feira": 0,
    "tuesday": 1,
    "terca": 1,
    "terca-feira": 1,
    "wednesday": 2,
    "quarta": 2,
    "quarta-feira": 2,
    "thursday": 3,
    "quinta": 3,
    "quinta-feira": 3,
    "friday": 4,
    "sexta": 4,
    "sexta-feira": 4,
    "saturday": 5,
    "sabado": 5,
    "sunday": 6,
    "domingo": 6,
}
Weekday = Annotated[int, Field(ge=0, le=6)]


class RankingHardConstraints(BaseModel):
    allowed_shifts: list[str] = Field(default_factory=list)
    excluded_weekdays: list[Weekday] = Field(default_factory=list)
    allowed_campuses: list[str] = Field(default_factory=list)
    earliest_start_time: time | None = None
    latest_end_time: time | None = None
    excluded_teacher_ids: list[uuid.UUID] = Field(default_factory=list)
    excluded_subject_ids: list[uuid.UUID] = Field(default_factory=list)
    max_subject_credits: float | None = Field(
        default=None,
        gt=0,
        le=30,
        validation_alias=AliasChoices("max_subject_credits", "max_credits"),
    )

    @field_validator("excluded_weekdays", mode="before")
    @classmethod
    def normalize_weekdays(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        normalized: list[Any] = []
        for item in value:
            if isinstance(item, str):
                key = item.strip().lower().replace("ç", "c").replace("á", "a")
                if key not in WEEKDAY_NAMES:
                    raise ValueError(f"dia da semana desconhecido: {item}")
                normalized.append(WEEKDAY_NAMES[key])
            else:
                normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def validate_time_window(self) -> "RankingHardConstraints":
        if (
            self.earliest_start_time is not None
            and self.latest_end_time is not None
            and self.earliest_start_time >= self.latest_end_time
        ):
            raise ValueError("earliest_start_time deve ser anterior a latest_end_time")
        return self


class RankingSoftPreferences(BaseModel):
    prefer_night: float = Field(default=0.0, ge=0, le=1)
    avoid_friday: float = Field(default=0.0, ge=0, le=1)
    avoid_early_classes: float = Field(default=0.0, ge=0, le=1)
    preferred_earliest_start: time = time(19, 0)
    prefer_fewer_campus_days: float = Field(default=0.0, ge=0, le=1)
    preferred_campuses: list[str] = Field(default_factory=list)


class RankingScoreWeights(BaseModel):
    curriculum_relevance: float = Field(default=0.35, ge=0, le=1)
    teacher: float = Field(default=0.25, ge=0, le=1)
    seat_probability: float = Field(default=0.25, ge=0, le=1)
    schedule_preference: float = Field(default=0.10, ge=0, le=1)
    workload: float = Field(default=0.05, ge=0, le=1)
    campus: float = Field(default=0.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_total(self) -> "RankingScoreWeights":
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 0.000001:
            raise ValueError("os pesos dos componentes do ranking devem somar 1")
        return self


class CurriculumRelevanceWeights(BaseModel):
    mandatory_ideal: float = Field(default=1.0, ge=0, le=1)
    mandatory: float = Field(default=0.9, ge=0, le=1)
    limited: float = Field(default=0.6, ge=0, le=1)
    free: float = Field(default=0.3, ge=0, le=1)
    not_applicable: float = Field(default=0.0, ge=0, le=1)
    unclassified: float = Field(default=0.0, ge=0, le=1)


class RankingTeacherStatisticsConfig(BaseModel):
    mode: TeacherStatisticsMode = TeacherStatisticsMode.BLENDED
    metric: TeacherScoreMetric = TeacherScoreMetric.AB_RATE
    use_bayesian_adjustment: bool = True
    prior_weight: float = Field(default=20.0, ge=0, le=10_000)
    confidence_constant: float = Field(default=20.0, gt=0, le=10_000)
    grade_weights: dict[str, float] = Field(default_factory=_default_grade_weights)
    missing_score: float = Field(default=50.0, ge=0, le=100)


class RankingConfig(BaseModel):
    course_strategy: CourseStrategy | None = None
    teacher_statistics: RankingTeacherStatisticsConfig = Field(
        default_factory=RankingTeacherStatisticsConfig
    )
    curriculum_weights: CurriculumRelevanceWeights = Field(
        default_factory=CurriculumRelevanceWeights
    )
    weights: RankingScoreWeights = Field(default_factory=RankingScoreWeights)
    missing_seat_probability_score: float = Field(default=50.0, ge=0, le=100)
    preferred_max_subject_credits: float = Field(default=6.0, gt=0, le=30)
    exclude_completed_subjects: bool = True
    exclude_in_progress_subjects: bool = True
    hard_constraints: RankingHardConstraints | None = None
    soft_preferences: RankingSoftPreferences | None = None


class SectionRankingRequest(BaseModel):
    term: str = Field(pattern=r"^[0-9]{4}:[1-3]$")
    student_id: uuid.UUID
    result_limit: int = Field(default=100, ge=1, le=2_000)
    config: RankingConfig = Field(default_factory=RankingConfig)


class RankingRerankRequest(BaseModel):
    result_limit: int | None = Field(default=None, ge=1, le=2_000)
    config: RankingConfig


class RankingCurriculumClassificationRead(BaseModel):
    course_id: uuid.UUID
    course_code: str
    curriculum_version_id: uuid.UUID
    curriculum_version: str
    category: CurriculumCategory | None
    category_source: CurriculumCategorySource | None
    ideal_term: int | None
    student_estimated_term: int
    credits: float | None
    relevance_score: float
    explanation: str


class RankingTeacherStatisticsRead(BaseModel):
    teacher_id: uuid.UUID
    teacher_name: str
    role: TeacherRole
    position: int
    score: float
    statistics_available: bool
    evaluation: TeacherStatisticsEvaluationRead


class EnrollmentPriorityCriterionRead(BaseModel):
    order: int = Field(ge=1)
    code: Literal["course", "shift", "cp", "ca"]
    value: str | float | bool | None
    status: Literal["favorable", "unfavorable", "informational", "unknown"]
    explanation: str


class EnrollmentPriorityRead(BaseModel):
    rule_version: str | None
    rule_effective_from: str | None
    rule_source_url: str | None
    phase: Literal["regular"] = "regular"
    offering_course_code: str | None
    offering_course_type: Literal["interdisciplinary", "specific", "unknown"]
    competition_pool: Literal[
        "general",
        "specific_linked",
        "specific_non_linked_20_percent",
        "unknown",
    ]
    course_priority: bool | None
    same_shift: bool | None
    cp: float | None
    ca: float | None
    criteria: list[EnrollmentPriorityCriterionRead]
    favorable_factors: list[str]
    risk_factors: list[str]
    missing_data: list[str]
    warnings: list[str]


class SeatProbabilityRead(BaseModel):
    estimated_probability: float | None
    personalized_probability: float | None
    probability_basis: Literal["aggregate_seats_over_requests", "unavailable"]
    score: float
    confidence: Literal["none", "low"]
    seats: int | None
    requests: int | None
    enrolled_count: int | None
    source: str
    favorable_factors: list[str]
    risk_factors: list[str]
    warnings: list[str]
    priority: EnrollmentPriorityRead


class RankingItemRead(BaseModel):
    id: uuid.UUID
    position: int
    section: SectionRead
    total_score: float
    score_breakdown: dict[str, float]
    curriculum_classifications: list[RankingCurriculumClassificationRead]
    teacher_statistics: list[RankingTeacherStatisticsRead]
    seat_probability: SeatProbabilityRead
    explanations: list[str]
    warnings: list[str]


class RankingRead(BaseModel):
    id: uuid.UUID
    term: str
    student_id: uuid.UUID
    source_ranking_id: uuid.UUID | None
    result_limit: int
    candidate_count: int
    item_count: int
    config: RankingConfig
    warnings: list[str]
    computed_at: datetime
    items: list[RankingItemRead]
