from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.enums import TeacherStatisticsMode
from app.models.statistics import TeacherStatistics, TeacherSubjectStatistics
from app.schemas.statistics import (
    GradeStatisticsRead,
    RateMetricsRead,
    TeacherStatisticsEvaluationRead,
    TeacherStatisticsEvaluationRequest,
)
from app.services.statistics.builder import RECENT_HISTORY_WARNING
from app.services.statistics.metrics import (
    GradeStatisticsResult,
    RateMetrics,
    blend_rate_metrics,
    calculate_grade_statistics,
    score_for_metric,
)


class TeacherStatisticsEvaluator:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(
        self, payload: TeacherStatisticsEvaluationRequest
    ) -> TeacherStatisticsEvaluationRead:
        general_row = self._find_general(payload)
        specific_row = self._find_specific(payload)
        return self.evaluate_from_rows(payload, general_row, specific_row)

    def evaluate_from_rows(
        self,
        payload: TeacherStatisticsEvaluationRequest,
        general_row: TeacherStatistics | None,
        specific_row: TeacherSubjectStatistics | None,
    ) -> TeacherStatisticsEvaluationRead:
        general = self._recalculate(general_row, payload) if general_row else None
        specific = self._recalculate(specific_row, payload) if specific_row else None
        warnings: list[str] = []

        if payload.mode == TeacherStatisticsMode.RECENT_HISTORY:
            return self._response(
                payload,
                general_row,
                specific_row,
                general,
                specific,
                warnings=[RECENT_HISTORY_WARNING],
            )

        selected: RateMetrics | None = None
        mode_used: TeacherStatisticsMode | None = None
        reliability: float | None = None
        selected_sample_size = 0

        if payload.mode == TeacherStatisticsMode.ALL_HISTORY:
            if general is not None:
                selected = _chosen_metrics(general, payload.use_bayesian_adjustment)
                selected_sample_size = general.sample_size
                mode_used = TeacherStatisticsMode.ALL_HISTORY
            else:
                warnings.append("nao ha estatistica geral para esse docente")
        elif payload.mode == TeacherStatisticsMode.SAME_SUBJECT:
            if specific is not None:
                selected = _chosen_metrics(specific, payload.use_bayesian_adjustment)
                selected_sample_size = specific.sample_size
                mode_used = TeacherStatisticsMode.SAME_SUBJECT
            else:
                warnings.append("nao ha estatistica desse docente nessa disciplina")
        else:
            selected, mode_used, reliability, selected_sample_size = self._blend(
                general, specific, payload, warnings
            )

        if (
            selected is not None
            and not payload.use_bayesian_adjustment
            and selected_sample_size < 10
        ):
            warnings.append("resultado bruto com amostra pequena; prefira o ajuste bayesiano")

        return self._response(
            payload,
            general_row,
            specific_row,
            general,
            specific,
            selected=selected,
            mode_used=mode_used,
            reliability=reliability,
            warnings=warnings,
        )

    def _find_general(
        self, payload: TeacherStatisticsEvaluationRequest
    ) -> TeacherStatistics | None:
        conditions: list[Any] = []
        if payload.teacher_id is not None:
            conditions.append(TeacherStatistics.teacher_id == payload.teacher_id)
        if payload.external_teacher_id is not None:
            conditions.append(TeacherStatistics.external_teacher_id == payload.external_teacher_id)
        return self.session.scalar(
            select(TeacherStatistics)
            .where(or_(*conditions))
            .order_by(
                TeacherStatistics.sample_size.desc(),
                TeacherStatistics.source_fetched_at.desc(),
            )
            .limit(1)
        )

    def _find_specific(
        self, payload: TeacherStatisticsEvaluationRequest
    ) -> TeacherSubjectStatistics | None:
        teacher_conditions: list[Any] = []
        subject_conditions: list[Any] = []
        if payload.teacher_id is not None:
            teacher_conditions.append(TeacherSubjectStatistics.teacher_id == payload.teacher_id)
        if payload.external_teacher_id is not None:
            teacher_conditions.append(
                TeacherSubjectStatistics.external_teacher_id == payload.external_teacher_id
            )
        if payload.subject_id is not None:
            subject_conditions.append(TeacherSubjectStatistics.subject_id == payload.subject_id)
        if payload.external_subject_id is not None:
            subject_conditions.append(
                TeacherSubjectStatistics.external_subject_id == payload.external_subject_id
            )
        if not subject_conditions:
            return None
        return self.session.scalar(
            select(TeacherSubjectStatistics)
            .where(and_(or_(*teacher_conditions), or_(*subject_conditions)))
            .order_by(
                TeacherSubjectStatistics.sample_size.desc(),
                TeacherSubjectStatistics.source_fetched_at.desc(),
            )
            .limit(1)
        )

    def _recalculate(
        self,
        row: TeacherStatistics | TeacherSubjectStatistics,
        payload: TeacherStatisticsEvaluationRequest,
    ) -> GradeStatisticsResult:
        return calculate_grade_statistics(
            row.grade_counts,
            reference_rates=row.reference_rates,
            prior_weight=payload.prior_weight,
            grade_weights=payload.grade_weights,
        )

    def _blend(
        self,
        general: GradeStatisticsResult | None,
        specific: GradeStatisticsResult | None,
        payload: TeacherStatisticsEvaluationRequest,
        warnings: list[str],
    ) -> tuple[RateMetrics | None, TeacherStatisticsMode | None, float | None, int]:
        if general is None and specific is None:
            warnings.append("nao ha estatistica disponivel para esse docente")
            return None, None, None, 0
        if specific is None:
            warnings.append("sem historico na disciplina; usando somente o historico geral")
            assert general is not None
            return (
                _chosen_metrics(general, payload.use_bayesian_adjustment),
                TeacherStatisticsMode.ALL_HISTORY,
                0.0,
                general.sample_size,
            )
        if general is None:
            warnings.append("sem historico geral; usando somente o historico na disciplina")
            return (
                _chosen_metrics(specific, payload.use_bayesian_adjustment),
                TeacherStatisticsMode.SAME_SUBJECT,
                1.0,
                specific.sample_size,
            )

        reliability = specific.sample_size / (specific.sample_size + payload.confidence_constant)
        selected = blend_rate_metrics(
            _chosen_metrics(general, payload.use_bayesian_adjustment),
            _chosen_metrics(specific, payload.use_bayesian_adjustment),
            reliability,
        )
        return (
            selected,
            TeacherStatisticsMode.BLENDED,
            reliability,
            general.sample_size + specific.sample_size,
        )

    def _response(
        self,
        payload: TeacherStatisticsEvaluationRequest,
        general_row: TeacherStatistics | None,
        specific_row: TeacherSubjectStatistics | None,
        general: GradeStatisticsResult | None,
        specific: GradeStatisticsResult | None,
        *,
        selected: RateMetrics | None = None,
        mode_used: TeacherStatisticsMode | None = None,
        reliability: float | None = None,
        warnings: Sequence[str] = (),
    ) -> TeacherStatisticsEvaluationRead:
        normalized_weights = (
            specific.grade_weights
            if specific is not None
            else general.grade_weights
            if general is not None
            else payload.grade_weights
        )
        return TeacherStatisticsEvaluationRead(
            available=selected is not None,
            requested_mode=payload.mode,
            mode_used=mode_used,
            metric=payload.metric,
            use_bayesian_adjustment=payload.use_bayesian_adjustment,
            score=(
                score_for_metric(
                    selected,
                    payload.metric,
                    normalized_weights,
                )
                if selected is not None
                else None
            ),
            selected_metrics=_metrics_read(selected) if selected is not None else None,
            general=(
                _statistics_read(general, general_row.source_fetched_at)
                if general is not None and general_row is not None
                else None
            ),
            specific=(
                _statistics_read(specific, specific_row.source_fetched_at)
                if specific is not None and specific_row is not None
                else None
            ),
            general_sample_size=general.sample_size if general is not None else 0,
            specific_sample_size=specific.sample_size if specific is not None else 0,
            reliability=reliability,
            external_teacher_id=(
                specific_row.external_teacher_id
                if specific_row is not None
                else general_row.external_teacher_id
                if general_row is not None
                else None
            ),
            external_subject_id=(
                specific_row.external_subject_id if specific_row is not None else None
            ),
            warnings=list(warnings),
        )


def _chosen_metrics(
    statistics: GradeStatisticsResult, use_bayesian_adjustment: bool
) -> RateMetrics:
    return statistics.adjusted if use_bayesian_adjustment else statistics.raw


def _metrics_read(metrics: RateMetrics) -> RateMetricsRead:
    return RateMetricsRead(
        a_rate=metrics.a_rate,
        ab_rate=metrics.ab_rate,
        failure_rate=metrics.failure_rate,
        fo_rate=metrics.fo_rate,
        mean_grade=metrics.mean_grade,
    )


def _statistics_read(
    statistics: GradeStatisticsResult, source_fetched_at: Any
) -> GradeStatisticsRead:
    return GradeStatisticsRead(
        grade_counts=statistics.grade_counts,
        sample_size=statistics.sample_size,
        effective_sample_size=statistics.effective_sample_size,
        confidence=statistics.confidence,
        prior_weight=statistics.prior_weight,
        reference_rates=statistics.reference_rates,
        grade_weights=statistics.grade_weights,
        raw=_metrics_read(statistics.raw),
        adjusted=_metrics_read(statistics.adjusted),
        source_fetched_at=source_fetched_at,
    )
