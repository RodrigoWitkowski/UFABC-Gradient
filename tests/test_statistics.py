from collections.abc import Generator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.enums import ExternalSyncStatus, StatisticsConfidence
from app.models.offerings import ExternalTeacherIdentifier, Subject, Teacher
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
    UfabcNextSyncRun,
)
from app.schemas.statistics import TeacherStatisticsEvaluationRequest
from app.services.normalization.text import normalize_text
from app.services.statistics import StatisticsBuilder, TeacherStatisticsEvaluator
from app.services.statistics.metrics import calculate_grade_statistics


@pytest.fixture
def api_client(session: Session) -> Generator[TestClient, None, None]:
    def override_database() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_database
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_bayesian_adjustment_reduces_small_sample_extremes() -> None:
    result = calculate_grade_statistics(
        {"A": 3},
        reference_rates={"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1},
        prior_weight=20,
    )

    assert result.sample_size == 3
    assert result.confidence == StatisticsConfidence.LOW
    assert result.raw.a_rate == 1
    assert result.adjusted.a_rate == pytest.approx(11 / 23)
    assert result.adjusted.a_rate < result.raw.a_rate


def test_grade_metrics_include_failure_and_custom_mean() -> None:
    result = calculate_grade_statistics(
        {"A": 2, "B": 1, "D": 1, "F": 1, "O": 1},
        prior_weight=0,
        grade_weights={"A": 4, "B": 3, "C": 2, "D": 1, "F": 0, "O": 0},
    )

    assert result.raw.ab_rate == pytest.approx(0.5)
    assert result.raw.failure_rate == pytest.approx(0.5)
    assert result.raw.fo_rate == pytest.approx(2 / 6)
    assert result.raw.mean_grade == pytest.approx(2.0)


def test_builder_and_evaluator_persist_explainable_statistics(session: Session) -> None:
    teacher, subject = _create_snapshots(session)

    build = StatisticsBuilder(session).rebuild()
    session.commit()

    assert build.teacher_statistics_count == 1
    assert build.subject_statistics_count == 1
    assert build.teacher_subject_statistics_count == 1
    assert build.recent_history_available is False
    assert "quadrimestre" in build.warnings[0]
    assert session.scalar(select(func.count()).select_from(TeacherTermStatistics)) == 0

    general_row = session.scalar(select(TeacherStatistics))
    subject_row = session.scalar(select(SubjectStatistics))
    specific_row = session.scalar(select(TeacherSubjectStatistics))
    assert general_row is not None
    assert subject_row is not None
    assert specific_row is not None
    assert general_row.teacher_id == teacher.id
    assert subject_row.subject_id == subject.id
    assert specific_row.grade_counts == {
        "A": 3,
        "B": 0,
        "C": 0,
        "D": 0,
        "F": 0,
        "O": 0,
    }

    evaluator = TeacherStatisticsEvaluator(session)
    blended = evaluator.evaluate(
        TeacherStatisticsEvaluationRequest(
            teacher_id=teacher.id,
            subject_id=subject.id,
            mode="blended",
        )
    )
    assert blended.available is True
    assert blended.mode_used == "blended"
    assert blended.general_sample_size == 4
    assert blended.specific_sample_size == 3
    assert blended.reliability == pytest.approx(3 / 23)
    assert blended.score is not None
    assert 0 <= blended.score <= 100

    raw_specific = evaluator.evaluate(
        TeacherStatisticsEvaluationRequest(
            external_teacher_id="teacher-next-1",
            external_subject_id="subject-next-1",
            mode="same_subject",
            use_bayesian_adjustment=False,
        )
    )
    assert raw_specific.available is True
    assert raw_specific.selected_metrics is not None
    assert raw_specific.selected_metrics.a_rate == 1
    assert any("amostra pequena" in warning for warning in raw_specific.warnings)

    recent = evaluator.evaluate(
        TeacherStatisticsEvaluationRequest(
            teacher_id=teacher.id,
            mode="recent_history",
        )
    )
    assert recent.available is False
    assert recent.mode_used is None
    assert "quadrimestre" in recent.warnings[0]


def test_statistics_api_rebuild_status_and_evaluate(
    api_client: TestClient, session: Session
) -> None:
    teacher, subject = _create_snapshots(session)

    rebuild = api_client.post("/statistics/rebuild", json={})

    assert rebuild.status_code == 201
    assert rebuild.json()["teacher_statistics_count"] == 1
    status = api_client.get("/statistics/status")
    assert status.status_code == 200
    assert status.json()["id"] == rebuild.json()["id"]

    evaluation = api_client.post(
        "/statistics/teachers/evaluate",
        json={
            "teacher_id": str(teacher.id),
            "subject_id": str(subject.id),
            "mode": "blended",
            "metric": "failure_rate",
        },
    )
    assert evaluation.status_code == 200
    payload = evaluation.json()
    assert payload["available"] is True
    assert payload["mode_used"] == "blended"
    assert payload["metric"] == "failure_rate"
    assert session.scalar(select(func.count()).select_from(StatisticsBuild)) == 1


def _create_snapshots(session: Session) -> tuple[Teacher, Subject]:
    fetched_at = datetime(2026, 7, 15, 12, 0)
    teacher = Teacher(
        canonical_name="Docente Estatistica",
        normalized_name=normalize_text("Docente Estatistica"),
    )
    subject = Subject(
        code="STAT001-23",
        name="Estatistica de Teste",
        normalized_name=normalize_text("Estatistica de Teste"),
    )
    teacher.external_identifiers.append(
        ExternalTeacherIdentifier(provider="ufabc_next", external_id="teacher-next-1")
    )
    session.add_all([teacher, subject])
    session.flush()
    session.add(
        ExternalSubjectIdentifier(
            subject_id=subject.id,
            provider="ufabc_next",
            external_id="subject-next-1",
        )
    )
    run = UfabcNextSyncRun(
        season="2026:3",
        status=ExternalSyncStatus.COMPLETED,
        started_at=fetched_at,
        finished_at=fetched_at,
    )
    session.add(run)
    session.flush()
    teacher_snapshot = TeacherReviewSnapshot(
        sync_run_id=run.id,
        teacher_id=teacher.id,
        external_teacher_id="teacher-next-1",
        sample_size=4,
        metrics={"count": 4},
        distribution=[
            {"conceito": "A", "count": 2},
            {"conceito": "C", "count": 2},
        ],
        specific_statistics=[
            {
                "_id": {"_id": "subject-next-1", "name": "Estatistica de Teste"},
                "count": 3,
                "distribution": [{"conceito": "A", "count": 3}],
            }
        ],
        fetched_at=fetched_at,
    )
    subject_snapshot = SubjectReviewSnapshot(
        sync_run_id=run.id,
        subject_id=subject.id,
        external_subject_id="subject-next-1",
        sample_size=10,
        metrics={"count": 10},
        distribution=[
            {"conceito": "A", "count": 5},
            {"conceito": "B", "count": 5},
        ],
        teacher_statistics=[
            {
                "_id": {"mainTeacher": "teacher-next-1"},
                "count": 8,
                "distribution": [{"conceito": "F", "count": 8}],
            }
        ],
        fetched_at=fetched_at,
    )
    session.add_all([teacher_snapshot, subject_snapshot])
    session.commit()
    return teacher, subject
