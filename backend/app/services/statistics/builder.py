from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.offerings import ExternalTeacherIdentifier
from app.models.statistics import (
    StatisticsBuild,
    SubjectStatistics,
    TeacherStatistics,
    TeacherSubjectStatistics,
    TeacherTermStatistics,
)
from app.models.ufabc_next import (
    ExternalSubjectIdentifier,
    SubjectReviewSnapshot,
    TeacherReviewSnapshot,
)
from app.services.statistics.metrics import (
    DEFAULT_GRADE_WEIGHTS,
    DEFAULT_REFERENCE_RATES,
    GradeStatisticsResult,
    aggregate_grade_counts,
    calculate_grade_statistics,
    rates_from_counts,
    sum_grade_counts,
)
from app.services.ufabc_next.cache import utc_now_naive

NEXT_PROVIDER = "ufabc_next"
RECENT_HISTORY_WARNING = (
    "recent_history indisponivel: os snapshots publicos do UFABC Next nao "
    "separam as avaliacoes por quadrimestre"
)


@dataclass(frozen=True)
class _SpecificCandidate:
    external_teacher_id: str
    external_subject_id: str
    counts: dict[str, int]
    fetched_at: datetime
    source_teacher_snapshot_id: uuid.UUID | None = None
    source_subject_snapshot_id: uuid.UUID | None = None

    @property
    def preference(self) -> tuple[datetime, int, int]:
        return (
            self.fetched_at,
            1 if self.source_teacher_snapshot_id is not None else 0,
            sum(self.counts.values()),
        )


class StatisticsBuilder:
    def __init__(self, session: Session) -> None:
        self.session = session

    def rebuild(
        self,
        *,
        prior_weight: float = 20.0,
        grade_weights: dict[str, float] | None = None,
    ) -> StatisticsBuild:
        weights = grade_weights or DEFAULT_GRADE_WEIGHTS
        # Validation and normalization happen in the shared calculator.
        normalized = calculate_grade_statistics(
            {}, prior_weight=prior_weight, grade_weights=weights
        )
        weights = normalized.grade_weights

        teacher_snapshots = self._latest_teacher_snapshots()
        subject_snapshots = self._latest_subject_snapshots()
        reference_rates = self._global_reference(teacher_snapshots, subject_snapshots)
        teacher_ids = self._teacher_identifiers()
        subject_ids = self._subject_identifiers()
        computed_at = utc_now_naive()

        self._clear_current_statistics()
        subject_statistics = self._build_subject_statistics(
            subject_snapshots,
            subject_ids,
            reference_rates,
            prior_weight,
            weights,
            computed_at,
        )
        teacher_statistics = self._build_teacher_statistics(
            teacher_snapshots,
            teacher_ids,
            reference_rates,
            prior_weight,
            weights,
            computed_at,
        )
        specific_statistics = self._build_specific_statistics(
            teacher_snapshots,
            subject_snapshots,
            teacher_ids,
            subject_ids,
            subject_statistics,
            reference_rates,
            prior_weight,
            weights,
            computed_at,
        )
        build = StatisticsBuild(
            prior_weight=_decimal(prior_weight),
            grade_weights=weights,
            teacher_statistics_count=len(teacher_statistics),
            subject_statistics_count=len(subject_statistics),
            teacher_subject_statistics_count=len(specific_statistics),
            recent_history_available=False,
            source_snapshot_counts={
                "teacher": len(teacher_snapshots),
                "subject": len(subject_snapshots),
            },
            warnings=[RECENT_HISTORY_WARNING],
            computed_at=computed_at,
        )
        self.session.add(build)
        self.session.flush()
        return build

    def _latest_teacher_snapshots(self) -> list[TeacherReviewSnapshot]:
        rows = self.session.scalars(
            select(TeacherReviewSnapshot).order_by(
                TeacherReviewSnapshot.external_teacher_id,
                TeacherReviewSnapshot.fetched_at.desc(),
                TeacherReviewSnapshot.created_at.desc(),
            )
        ).all()
        return list(_latest_by_external_id(rows, "external_teacher_id").values())

    def _latest_subject_snapshots(self) -> list[SubjectReviewSnapshot]:
        rows = self.session.scalars(
            select(SubjectReviewSnapshot).order_by(
                SubjectReviewSnapshot.external_subject_id,
                SubjectReviewSnapshot.fetched_at.desc(),
                SubjectReviewSnapshot.created_at.desc(),
            )
        ).all()
        return list(_latest_by_external_id(rows, "external_subject_id").values())

    def _teacher_identifiers(self) -> dict[str, uuid.UUID]:
        identifiers = self.session.scalars(
            select(ExternalTeacherIdentifier).where(
                ExternalTeacherIdentifier.provider == NEXT_PROVIDER
            )
        ).all()
        return {item.external_id: item.teacher_id for item in identifiers}

    def _subject_identifiers(self) -> dict[str, uuid.UUID]:
        identifiers = self.session.scalars(
            select(ExternalSubjectIdentifier).where(
                ExternalSubjectIdentifier.provider == NEXT_PROVIDER
            )
        ).all()
        grouped: dict[str, set[uuid.UUID]] = {}
        for item in identifiers:
            grouped.setdefault(item.external_id, set()).add(item.subject_id)
        return {
            external_id: next(iter(ids)) for external_id, ids in grouped.items() if len(ids) == 1
        }

    def _global_reference(
        self,
        teacher_snapshots: list[TeacherReviewSnapshot],
        subject_snapshots: list[SubjectReviewSnapshot],
    ) -> dict[str, float]:
        source = subject_snapshots or teacher_snapshots
        counts = sum_grade_counts(
            *(aggregate_grade_counts(snapshot.distribution) for snapshot in source)
        )
        if not any(counts.values()):
            return DEFAULT_REFERENCE_RATES.copy()
        return rates_from_counts(counts)

    def _clear_current_statistics(self) -> None:
        self.session.execute(delete(TeacherTermStatistics))
        self.session.execute(delete(TeacherSubjectStatistics))
        self.session.execute(delete(TeacherStatistics))
        self.session.execute(delete(SubjectStatistics))

    def _build_subject_statistics(
        self,
        snapshots: list[SubjectReviewSnapshot],
        subject_ids: dict[str, uuid.UUID],
        reference_rates: dict[str, float],
        prior_weight: float,
        grade_weights: dict[str, float],
        computed_at: datetime,
    ) -> dict[str, SubjectStatistics]:
        result: dict[str, SubjectStatistics] = {}
        for snapshot in snapshots:
            calculated = calculate_grade_statistics(
                aggregate_grade_counts(snapshot.distribution),
                reference_rates=reference_rates,
                prior_weight=prior_weight,
                grade_weights=grade_weights,
            )
            row = SubjectStatistics(
                subject_id=snapshot.subject_id or subject_ids.get(snapshot.external_subject_id),
                external_subject_id=snapshot.external_subject_id,
                source_snapshot_id=snapshot.id,
                source_fetched_at=snapshot.fetched_at,
                computed_at=computed_at,
                **_statistics_values(calculated),
            )
            self.session.add(row)
            result[snapshot.external_subject_id] = row
        return result

    def _build_teacher_statistics(
        self,
        snapshots: list[TeacherReviewSnapshot],
        teacher_ids: dict[str, uuid.UUID],
        reference_rates: dict[str, float],
        prior_weight: float,
        grade_weights: dict[str, float],
        computed_at: datetime,
    ) -> dict[str, TeacherStatistics]:
        result: dict[str, TeacherStatistics] = {}
        for snapshot in snapshots:
            calculated = calculate_grade_statistics(
                aggregate_grade_counts(snapshot.distribution),
                reference_rates=reference_rates,
                prior_weight=prior_weight,
                grade_weights=grade_weights,
            )
            row = TeacherStatistics(
                teacher_id=snapshot.teacher_id or teacher_ids.get(snapshot.external_teacher_id),
                external_teacher_id=snapshot.external_teacher_id,
                source_snapshot_id=snapshot.id,
                source_fetched_at=snapshot.fetched_at,
                computed_at=computed_at,
                **_statistics_values(calculated),
            )
            self.session.add(row)
            result[snapshot.external_teacher_id] = row
        return result

    def _build_specific_statistics(
        self,
        teacher_snapshots: list[TeacherReviewSnapshot],
        subject_snapshots: list[SubjectReviewSnapshot],
        teacher_ids: dict[str, uuid.UUID],
        subject_ids: dict[str, uuid.UUID],
        subject_statistics: dict[str, SubjectStatistics],
        global_reference: dict[str, float],
        prior_weight: float,
        grade_weights: dict[str, float],
        computed_at: datetime,
    ) -> list[TeacherSubjectStatistics]:
        candidates: dict[tuple[str, str], _SpecificCandidate] = {}
        for teacher_snapshot in teacher_snapshots:
            for item in teacher_snapshot.specific_statistics:
                external_subject_id = _external_subject_id(item)
                if external_subject_id is None:
                    continue
                candidate = _SpecificCandidate(
                    external_teacher_id=teacher_snapshot.external_teacher_id,
                    external_subject_id=external_subject_id,
                    counts=aggregate_grade_counts(item.get("distribution")),
                    fetched_at=teacher_snapshot.fetched_at,
                    source_teacher_snapshot_id=teacher_snapshot.id,
                )
                _prefer_candidate(candidates, candidate)
        for subject_snapshot in subject_snapshots:
            for item in subject_snapshot.teacher_statistics:
                external_teacher_id = _external_teacher_id(item)
                if external_teacher_id is None:
                    continue
                candidate = _SpecificCandidate(
                    external_teacher_id=external_teacher_id,
                    external_subject_id=subject_snapshot.external_subject_id,
                    counts=aggregate_grade_counts(item.get("distribution")),
                    fetched_at=subject_snapshot.fetched_at,
                    source_subject_snapshot_id=subject_snapshot.id,
                )
                _prefer_candidate(candidates, candidate)

        result: list[TeacherSubjectStatistics] = []
        for candidate in candidates.values():
            if not any(candidate.counts.values()):
                continue
            subject_statistic = subject_statistics.get(candidate.external_subject_id)
            reference = (
                rates_from_counts(subject_statistic.grade_counts)
                if subject_statistic is not None
                else global_reference
            )
            calculated = calculate_grade_statistics(
                candidate.counts,
                reference_rates=reference,
                prior_weight=prior_weight,
                grade_weights=grade_weights,
            )
            row = TeacherSubjectStatistics(
                teacher_id=teacher_ids.get(candidate.external_teacher_id),
                subject_id=subject_ids.get(candidate.external_subject_id),
                external_teacher_id=candidate.external_teacher_id,
                external_subject_id=candidate.external_subject_id,
                source_teacher_snapshot_id=candidate.source_teacher_snapshot_id,
                source_subject_snapshot_id=candidate.source_subject_snapshot_id,
                source_fetched_at=candidate.fetched_at,
                computed_at=computed_at,
                **_statistics_values(calculated),
            )
            self.session.add(row)
            result.append(row)
        return result


def _latest_by_external_id(rows: Sequence[Any], attribute: str) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for row in rows:
        latest.setdefault(str(getattr(row, attribute)), row)
    return latest


def _prefer_candidate(
    candidates: dict[tuple[str, str], _SpecificCandidate],
    candidate: _SpecificCandidate,
) -> None:
    key = (candidate.external_teacher_id, candidate.external_subject_id)
    current = candidates.get(key)
    if current is None or candidate.preference > current.preference:
        candidates[key] = candidate


def _external_subject_id(item: dict[str, Any]) -> str | None:
    candidates = [item.get("_id"), item.get("subject")]
    for candidate in candidates:
        if isinstance(candidate, dict):
            value = candidate.get("_id") or candidate.get("subjectId")
        else:
            value = candidate
        if isinstance(value, str) and value:
            return value
    return None


def _external_teacher_id(item: dict[str, Any]) -> str | None:
    identifier = item.get("_id")
    candidates: list[Any] = []
    if isinstance(identifier, dict):
        candidates.append(identifier.get("mainTeacher"))
    candidates.extend([item.get("teacher"), item.get("mainTeacher")])
    for candidate in candidates:
        value = candidate.get("_id") if isinstance(candidate, dict) else candidate
        if isinstance(value, str) and value:
            return value
    return None


def _statistics_values(result: GradeStatisticsResult) -> dict[str, Any]:
    return {
        "grade_counts": result.grade_counts,
        "sample_size": result.sample_size,
        "effective_sample_size": _decimal(result.effective_sample_size),
        "raw_a_rate": _decimal(result.raw.a_rate),
        "adjusted_a_rate": _decimal(result.adjusted.a_rate),
        "raw_ab_rate": _decimal(result.raw.ab_rate),
        "adjusted_ab_rate": _decimal(result.adjusted.ab_rate),
        "raw_failure_rate": _decimal(result.raw.failure_rate),
        "adjusted_failure_rate": _decimal(result.adjusted.failure_rate),
        "raw_fo_rate": _decimal(result.raw.fo_rate),
        "adjusted_fo_rate": _decimal(result.adjusted.fo_rate),
        "raw_mean_grade": _decimal(result.raw.mean_grade),
        "adjusted_mean_grade": _decimal(result.adjusted.mean_grade),
        "confidence": result.confidence,
        "prior_weight": _decimal(result.prior_weight),
        "reference_rates": result.reference_rates,
        "grade_weights": result.grade_weights,
    }


def _decimal(value: float | int) -> Decimal:
    return Decimal(str(value))
