import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    StatisticsConfidence,
    TeacherScoreMetric,
    TeacherStatisticsMode,
)


def _default_grade_weights() -> dict[str, float]:
    return {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0, "O": 0.0}


class StatisticsBuildRequest(BaseModel):
    prior_weight: float = Field(default=20.0, ge=0, le=10_000)
    grade_weights: dict[str, float] = Field(default_factory=_default_grade_weights)


class StatisticsBuildRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prior_weight: float
    grade_weights: dict[str, float]
    teacher_statistics_count: int
    subject_statistics_count: int
    teacher_subject_statistics_count: int
    recent_history_available: bool
    source_snapshot_counts: dict[str, int]
    warnings: list[str]
    computed_at: datetime


class RateMetricsRead(BaseModel):
    a_rate: float
    ab_rate: float
    failure_rate: float
    fo_rate: float
    mean_grade: float


class GradeStatisticsRead(BaseModel):
    grade_counts: dict[str, int]
    sample_size: int
    effective_sample_size: float
    confidence: StatisticsConfidence
    prior_weight: float
    reference_rates: dict[str, float]
    grade_weights: dict[str, float]
    raw: RateMetricsRead
    adjusted: RateMetricsRead
    source_fetched_at: datetime


class TeacherStatisticsEvaluationRequest(BaseModel):
    teacher_id: uuid.UUID | None = None
    external_teacher_id: str | None = Field(default=None, min_length=1, max_length=255)
    subject_id: uuid.UUID | None = None
    external_subject_id: str | None = Field(default=None, min_length=1, max_length=255)
    mode: TeacherStatisticsMode = TeacherStatisticsMode.BLENDED
    metric: TeacherScoreMetric = TeacherScoreMetric.AB_RATE
    use_bayesian_adjustment: bool = True
    prior_weight: float = Field(default=20.0, ge=0, le=10_000)
    confidence_constant: float = Field(default=20.0, gt=0, le=10_000)
    grade_weights: dict[str, float] = Field(default_factory=_default_grade_weights)

    @model_validator(mode="after")
    def validate_identifiers(self) -> "TeacherStatisticsEvaluationRequest":
        if self.teacher_id is None and self.external_teacher_id is None:
            raise ValueError("informe teacher_id ou external_teacher_id")
        if self.mode == TeacherStatisticsMode.SAME_SUBJECT:
            if self.subject_id is None and self.external_subject_id is None:
                raise ValueError("same_subject exige subject_id ou external_subject_id")
        return self


class TeacherStatisticsEvaluationRead(BaseModel):
    available: bool
    requested_mode: TeacherStatisticsMode
    mode_used: TeacherStatisticsMode | None
    metric: TeacherScoreMetric
    use_bayesian_adjustment: bool
    score: float | None
    selected_metrics: RateMetricsRead | None
    general: GradeStatisticsRead | None
    specific: GradeStatisticsRead | None
    general_sample_size: int
    specific_sample_size: int
    reliability: float | None
    external_teacher_id: str | None
    external_subject_id: str | None
    warnings: list[str]
