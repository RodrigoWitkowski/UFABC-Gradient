from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from app.models.enums import StatisticsConfidence, TeacherScoreMetric

GRADES = ("A", "B", "C", "D", "F", "O")
DEFAULT_GRADE_WEIGHTS = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0, "O": 0.0}
DEFAULT_REFERENCE_RATES = {
    "A": 0.25,
    "B": 0.25,
    "C": 0.20,
    "D": 0.10,
    "F": 0.10,
    "O": 0.10,
}


@dataclass(frozen=True)
class RateMetrics:
    a_rate: float
    ab_rate: float
    failure_rate: float
    fo_rate: float
    mean_grade: float


@dataclass(frozen=True)
class GradeStatisticsResult:
    grade_counts: dict[str, int]
    sample_size: int
    effective_sample_size: float
    raw: RateMetrics
    adjusted: RateMetrics
    confidence: StatisticsConfidence
    prior_weight: float
    reference_rates: dict[str, float]
    grade_weights: dict[str, float]


def aggregate_grade_counts(distribution: Any) -> dict[str, int]:
    counts = {grade: 0 for grade in GRADES}
    if not isinstance(distribution, list):
        return counts
    for item in distribution:
        if not isinstance(item, dict):
            continue
        grade = str(item.get("conceito", "")).strip().upper()
        if grade not in counts:
            continue
        count = item.get("count")
        if isinstance(count, bool) or not isinstance(count, int | float | str):
            continue
        try:
            parsed_count = int(count)
        except (TypeError, ValueError):
            continue
        if parsed_count > 0:
            counts[grade] += parsed_count
    return counts


def sum_grade_counts(*values: dict[str, int]) -> dict[str, int]:
    return {grade: sum(max(item.get(grade, 0), 0) for item in values) for grade in GRADES}


def rates_from_counts(counts: dict[str, int]) -> dict[str, float]:
    normalized = _normalized_counts(counts)
    total = sum(normalized.values())
    if total == 0:
        return DEFAULT_REFERENCE_RATES.copy()
    return {grade: normalized[grade] / total for grade in GRADES}


def calculate_grade_statistics(
    counts: dict[str, int],
    *,
    reference_rates: dict[str, float] | None = None,
    prior_weight: float = 20.0,
    grade_weights: dict[str, float] | None = None,
) -> GradeStatisticsResult:
    if prior_weight < 0:
        raise ValueError("prior_weight nao pode ser negativo")
    normalized_counts = _normalized_counts(counts)
    weights = _normalized_weights(grade_weights or DEFAULT_GRADE_WEIGHTS)
    reference = _normalized_reference(reference_rates or DEFAULT_REFERENCE_RATES)
    sample_size = sum(normalized_counts.values())
    raw_rates = (
        {grade: normalized_counts[grade] / sample_size for grade in GRADES}
        if sample_size
        else {grade: 0.0 for grade in GRADES}
    )
    denominator = sample_size + prior_weight
    adjusted_rates = (
        {
            grade: (normalized_counts[grade] + prior_weight * reference[grade]) / denominator
            for grade in GRADES
        }
        if denominator
        else raw_rates
    )
    return GradeStatisticsResult(
        grade_counts=normalized_counts,
        sample_size=sample_size,
        effective_sample_size=denominator,
        raw=_rate_metrics(raw_rates, weights),
        adjusted=_rate_metrics(adjusted_rates, weights),
        confidence=confidence_for_sample(sample_size),
        prior_weight=prior_weight,
        reference_rates=reference,
        grade_weights=weights,
    )


def confidence_for_sample(sample_size: int) -> StatisticsConfidence:
    if sample_size <= 0:
        return StatisticsConfidence.NONE
    if sample_size < 10:
        return StatisticsConfidence.LOW
    if sample_size < 30:
        return StatisticsConfidence.MEDIUM
    return StatisticsConfidence.HIGH


def blend_rate_metrics(
    general: RateMetrics,
    specific: RateMetrics,
    reliability: float,
) -> RateMetrics:
    weight = min(max(reliability, 0.0), 1.0)
    return RateMetrics(
        a_rate=weight * specific.a_rate + (1 - weight) * general.a_rate,
        ab_rate=weight * specific.ab_rate + (1 - weight) * general.ab_rate,
        failure_rate=(weight * specific.failure_rate + (1 - weight) * general.failure_rate),
        fo_rate=weight * specific.fo_rate + (1 - weight) * general.fo_rate,
        mean_grade=weight * specific.mean_grade + (1 - weight) * general.mean_grade,
    )


def score_for_metric(
    metrics: RateMetrics,
    metric: TeacherScoreMetric,
    grade_weights: dict[str, float],
) -> float:
    if metric == TeacherScoreMetric.A_RATE:
        score = metrics.a_rate
    elif metric == TeacherScoreMetric.AB_RATE:
        score = metrics.ab_rate
    elif metric == TeacherScoreMetric.FAILURE_RATE:
        score = 1 - metrics.failure_rate
    elif metric == TeacherScoreMetric.FO_RATE:
        score = 1 - metrics.fo_rate
    else:
        maximum = max(grade_weights.values(), default=0)
        score = metrics.mean_grade / maximum if maximum > 0 else 0
    return round(min(max(score, 0.0), 1.0) * 100, 6)


def _normalized_counts(counts: dict[str, int]) -> dict[str, int]:
    return {grade: max(int(counts.get(grade, 0)), 0) for grade in GRADES}


def _normalized_weights(weights: dict[str, float]) -> dict[str, float]:
    values = {grade: float(weights.get(grade, DEFAULT_GRADE_WEIGHTS[grade])) for grade in GRADES}
    if any(not isfinite(value) or value < 0 for value in values.values()):
        raise ValueError("grade_weights deve conter somente valores finitos e nao negativos")
    return values


def _normalized_reference(reference: dict[str, float]) -> dict[str, float]:
    values = {grade: max(float(reference.get(grade, 0)), 0.0) for grade in GRADES}
    total = sum(values.values())
    if total <= 0:
        return DEFAULT_REFERENCE_RATES.copy()
    return {grade: values[grade] / total for grade in GRADES}


def _rate_metrics(rates: dict[str, float], weights: dict[str, float]) -> RateMetrics:
    return RateMetrics(
        a_rate=rates["A"],
        ab_rate=rates["A"] + rates["B"],
        failure_rate=rates["D"] + rates["F"] + rates["O"],
        fo_rate=rates["F"] + rates["O"],
        mean_grade=sum(rates[grade] * weights[grade] for grade in GRADES),
    )
