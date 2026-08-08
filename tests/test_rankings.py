from collections.abc import Generator
from datetime import datetime, time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.curriculum import Course, CourseCurriculumSubject, CurriculumVersion
from app.models.enums import (
    CourseStrategy,
    CurriculumCategory,
    CurriculumCategorySource,
    ExternalSyncStatus,
    ImportStatus,
    MeetingFrequency,
    MeetingType,
    TeacherRole,
)
from app.models.imports import ImportBatch, ImportFile, Term
from app.models.offerings import (
    Section,
    SectionCourseOffering,
    SectionMeeting,
    SectionTeacher,
    Subject,
    Teacher,
)
from app.models.rankings import Ranking, RankingItem
from app.models.statistics import TeacherStatistics
from app.models.students import (
    StudentCompletedSubject,
    StudentCourse,
    StudentPreference,
    StudentProfile,
)
from app.models.ufabc_next import UfabcNextComponentSnapshot, UfabcNextSyncRun
from app.schemas.rankings import (
    LocalPopulationProbabilityConfig,
    RankingConfig,
    RankingHardConstraints,
    RankingRerankRequest,
    RankingScoreWeights,
    RankingSoftPreferences,
    SectionRankingRequest,
)
from app.services.normalization.text import normalize_text
from app.services.rankings import RankingService
from app.services.statistics.metrics import GradeStatisticsResult, calculate_grade_statistics


@pytest.fixture
def api_client(session: Session) -> Generator[TestClient, None, None]:
    def override_database() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_database
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_default_ranking_weights_ignore_subject_credits() -> None:
    weights = RankingScoreWeights()

    assert weights.curriculum_relevance == pytest.approx(0.375)
    assert weights.schedule_preference == pytest.approx(0.125)
    assert weights.workload == 0
    assert sum(weights.model_dump().values()) == pytest.approx(1)


def test_ranking_is_explainable_and_reranking_preserves_original(session: Session) -> None:
    student, mandatory_section, free_section = _create_ranking_scenario(session)
    service = RankingService(session)
    curriculum_only = RankingConfig(
        weights=RankingScoreWeights(
            curriculum_relevance=1,
            teacher=0,
            seat_probability=0,
            schedule_preference=0,
            workload=0,
            campus=0,
        )
    )

    original = service.create_ranking(
        SectionRankingRequest(
            term="2026:3",
            student_id=student.id,
            result_limit=10,
            config=curriculum_only,
        )
    )
    session.commit()
    original_read = service.serialize(service.get_ranking(original.id))

    assert original_read.candidate_count == 2
    assert original_read.item_count == 2
    assert original_read.items[0].section.id == mandatory_section.id
    assert original_read.items[0].score_breakdown["curriculum_relevance"] == 100
    assert original_read.items[0].seat_probability.estimated_probability == pytest.approx(0.2)
    assert original_read.items[0].seat_probability.personalized_probability is None
    assert original_read.items[0].seat_probability.confidence == "low"
    priority = original_read.items[0].seat_probability.priority
    assert priority.rule_version == "consepe-260-2023"
    assert priority.offering_course_type == "interdisciplinary"
    assert priority.course_priority is True
    assert priority.same_shift is True
    assert priority.cp == pytest.approx(0.95)
    assert priority.ca == pytest.approx(3.4)
    assert all(item.code != "campus" for item in priority.criteria)
    free_item = next(item for item in original_read.items if item.section.id == free_section.id)
    assert free_item.curriculum_classifications[0].category == CurriculumCategory.FREE
    assert free_item.curriculum_classifications[0].category_source == (
        CurriculumCategorySource.DERIVED_RULE
    )
    assert free_item.seat_probability.estimated_probability is None
    assert any("Demanda igual a zero" in warning for warning in free_item.warnings)

    teacher_only = RankingConfig(
        sort_mode="weighted_score",
        weights=RankingScoreWeights(
            curriculum_relevance=0,
            teacher=1,
            seat_probability=0,
            schedule_preference=0,
            workload=0,
            campus=0,
        )
    )
    reranked = service.rerank(
        original.id,
        RankingRerankRequest(config=teacher_only),
    )
    session.commit()

    reranked_read = service.serialize(service.get_ranking(reranked.id))
    assert reranked_read.source_ranking_id == original.id
    assert reranked_read.items[0].section.id == free_section.id
    assert reranked_read.items[0].teacher_statistics[0].statistics_available is True
    assert reranked_read.items[0].teacher_statistics[0].score > (
        reranked_read.items[1].teacher_statistics[0].score
    )
    assert service.serialize(service.get_ranking(original.id)).items[0].section.id == (
        mandatory_section.id
    )
    assert session.scalar(select(func.count()).select_from(Ranking)) == 2
    assert session.scalar(select(func.count()).select_from(RankingItem)) == 4


def test_ranking_api_create_get_and_rerank(api_client: TestClient, session: Session) -> None:
    student, mandatory_section, free_section = _create_ranking_scenario(session)
    curriculum_weights = _single_component_weights("curriculum_relevance")

    created = api_client.post(
        "/rankings/sections",
        json={
            "term": "2026:3",
            "student_id": str(student.id),
            "result_limit": 10,
            "config": {"weights": curriculum_weights},
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["items"][0]["section"]["id"] == str(mandatory_section.id)
    assert payload["candidate_count"] == 2
    loaded = api_client.get(f"/rankings/{payload['id']}")
    assert loaded.status_code == 200
    assert loaded.json()["id"] == payload["id"]

    reranked = api_client.post(
        f"/rankings/{payload['id']}/rerank",
        json={
            "config": {
                "sort_mode": "weighted_score",
                "weights": _single_component_weights("teacher"),
            }
        },
    )
    assert reranked.status_code == 201
    reranked_payload = reranked.json()
    assert reranked_payload["source_ranking_id"] == payload["id"]
    assert reranked_payload["items"][0]["section"]["id"] == str(free_section.id)

    filtered = api_client.post(
        "/rankings/sections",
        json={
            "term": "2026:3",
            "student_id": str(student.id),
            "config": {
                "hard_constraints": {
                    "excluded_teacher_ids": [str(mandatory_section.teachers[0].teacher_id)]
                }
            },
        },
    )
    assert filtered.status_code == 201
    assert filtered.json()["candidate_count"] == 1
    assert filtered.json()["items"][0]["section"]["id"] == str(free_section.id)


def test_probability_first_is_default_when_probability_and_teacher_conflict(
    session: Session,
) -> None:
    student, mandatory_section, free_section = _create_ranking_scenario(session)
    service = RankingService(session)

    ranking = service.create_ranking(
        SectionRankingRequest(
            term="2026:3",
            student_id=student.id,
            config=RankingConfig(
                weights=RankingScoreWeights(
                    curriculum_relevance=0,
                    teacher=1,
                    seat_probability=0,
                    schedule_preference=0,
                    workload=0,
                    campus=0,
                )
            ),
        )
    )
    session.commit()
    result = service.serialize(service.get_ranking(ranking.id))

    assert result.items[0].section.id == mandatory_section.id
    assert result.items[0].seat_probability.summary
    assert result.items[0].seat_probability.estimated_probability == pytest.approx(0.2)
    assert result.items[1].teacher_statistics[0].score > result.items[0].teacher_statistics[0].score


def test_saved_hard_constraints_filter_and_explicit_config_replaces_them(
    session: Session,
) -> None:
    student, mandatory_section, free_section = _create_ranking_scenario(session)
    student.preferences = StudentPreference(
        hard_constraints={"excluded_weekdays": ["friday"]},
        soft_preferences={},
    )
    session.commit()
    service = RankingService(session)

    saved_preferences = service.create_ranking(
        SectionRankingRequest(term="2026:3", student_id=student.id)
    )
    session.commit()
    saved_read = service.serialize(service.get_ranking(saved_preferences.id))

    assert saved_read.candidate_count == 1
    assert saved_read.items[0].section.id == free_section.id
    assert saved_read.config.hard_constraints is not None
    assert saved_read.config.hard_constraints.excluded_weekdays == [4]
    assert any("dia da semana excluido" in warning for warning in saved_read.warnings)

    explicit_empty = service.create_ranking(
        SectionRankingRequest(
            term="2026:3",
            student_id=student.id,
            config=RankingConfig(hard_constraints=RankingHardConstraints()),
        )
    )
    session.commit()
    explicit_read = service.serialize(service.get_ranking(explicit_empty.id))
    assert explicit_read.candidate_count == 2
    assert {item.section.id for item in explicit_read.items} == {
        mandatory_section.id,
        free_section.id,
    }


def test_soft_preferences_change_score_without_removing_sections(session: Session) -> None:
    student, mandatory_section, free_section = _create_ranking_scenario(session)
    schedule_only = RankingConfig(
        weights=RankingScoreWeights(
            curriculum_relevance=0,
            teacher=0,
            seat_probability=0,
            schedule_preference=1,
            workload=0,
            campus=0,
        ),
        soft_preferences=RankingSoftPreferences(prefer_night=1),
    )

    service = RankingService(session)
    ranking = service.create_ranking(
        SectionRankingRequest(
            term="2026:3",
            student_id=student.id,
            config=schedule_only,
        )
    )
    session.commit()
    result = service.serialize(service.get_ranking(ranking.id))

    assert result.candidate_count == 2
    assert result.items[0].section.id == mandatory_section.id
    assert (
        result.items[0].score_breakdown["schedule_preference"]
        > (result.items[1].score_breakdown["schedule_preference"])
    )
    assert {item.section.id for item in result.items} == {
        mandatory_section.id,
        free_section.id,
    }


def test_local_population_probability_can_drive_ranking(session: Session) -> None:
    student, mandatory_section, free_section = _create_ranking_scenario(session)
    mandatory_section.total_seats = 1
    free_section.total_seats = 1
    session.add(
        StudentProfile(
            display_name="Concorrente Forte",
            admission_year=2026,
            admission_shift="Noturno",
            campus="SA",
            ca=Decimal("3.8"),
            accumulated_credits=Decimal(0),
            course_strategy=CourseStrategy.PRIMARY_COURSE,
            courses=[
                StudentCourse(
                    course=student.courses[0].course,
                    curriculum_version=student.courses[0].curriculum_version,
                    is_primary=True,
                    cp=Decimal("0.99"),
                )
            ],
        )
    )
    session.commit()

    service = RankingService(session)
    ranking = service.create_ranking(
        SectionRankingRequest(
            term="2026:3",
            student_id=student.id,
            config=RankingConfig(
                weights=RankingScoreWeights(
                    curriculum_relevance=0,
                    teacher=0,
                    seat_probability=1,
                    schedule_preference=0,
                    workload=0,
                    campus=0,
                ),
                local_population_probability=LocalPopulationProbabilityConfig(
                    min_population_size=1,
                    simulations=400,
                ),
            ),
        )
    )
    session.commit()
    result = service.serialize(service.get_ranking(ranking.id))

    assert result.items[0].section.id == free_section.id
    assert result.items[0].seat_probability.personalized_probability is not None
    assert result.items[1].seat_probability.personalized_probability is not None
    assert (
        result.items[0].seat_probability.personalized_probability
        > result.items[1].seat_probability.personalized_probability
    )
    assert result.items[0].seat_probability.probability_basis == "local_population_monte_carlo"
    assert result.items[1].seat_probability.estimated_probability == pytest.approx(0.2)


def test_specific_course_uses_non_linked_twenty_percent_pool(session: Session) -> None:
    student, _mandatory_section, free_section = _create_ranking_scenario(session)
    bcc = Course(
        code="BCC",
        name="Bacharelado em Ciencia da Computacao",
        normalized_name=normalize_text("Bacharelado em Ciencia da Computacao"),
    )
    session.add(bcc)
    free_section.course_links.clear()
    session.flush()
    free_section.course_links.append(SectionCourseOffering(course=bcc))
    session.commit()

    service = RankingService(session)
    ranking = service.create_ranking(
        SectionRankingRequest(term="2026:3", student_id=student.id)
    )
    session.commit()
    result = service.serialize(service.get_ranking(ranking.id))
    free_item = next(item for item in result.items if item.section.id == free_section.id)
    priority = free_item.seat_probability.priority

    assert priority.offering_course_code == "BCC"
    assert priority.offering_course_type == "specific"
    assert priority.competition_pool == "specific_non_linked_20_percent"
    assert priority.course_priority is False
    assert any("20%" in item.explanation for item in priority.criteria)


def _single_component_weights(component: str) -> dict[str, float]:
    names = {
        "curriculum_relevance",
        "teacher",
        "seat_probability",
        "schedule_preference",
        "workload",
        "campus",
    }
    return {name: 1.0 if name == component else 0.0 for name in names}


def _create_ranking_scenario(session: Session) -> tuple[StudentProfile, Section, Section]:
    now = datetime(2026, 7, 16, 12, 0)
    term = Term(code="2026:3", year=2026, term_number=3)
    import_file = ImportFile(
        original_filename="ranking.csv",
        stored_path="var/ranking.csv",
        sha256="r" * 64,
        size_bytes=1,
        content_type="text/csv",
    )
    batch = ImportBatch(
        import_file=import_file,
        term=term,
        status=ImportStatus.COMPLETED,
        parser_config={},
    )
    mandatory_subject = Subject(
        code="MAND001-23",
        name="Obrigatoria",
        normalized_name=normalize_text("Obrigatoria"),
    )
    free_subject = Subject(
        code="FREE001-23",
        name="Livre",
        normalized_name=normalize_text("Livre"),
    )
    completed_subject = Subject(
        code="DONE001-23",
        name="Concluida",
        normalized_name=normalize_text("Concluida"),
    )
    course = Course(
        code="BCT",
        name="Bacharelado em Ciencia e Tecnologia",
        normalized_name=normalize_text("Bacharelado em Ciencia e Tecnologia"),
    )
    curriculum = CurriculumVersion(
        course=course,
        version="2026",
        admission_year_start=2026,
        unlisted_subject_category=CurriculumCategory.FREE,
    )
    curriculum.subjects.append(
        CourseCurriculumSubject(
            subject=mandatory_subject,
            category=CurriculumCategory.MANDATORY,
            category_source=CurriculumCategorySource.EXPLICIT,
            ideal_term=3,
            credits=Decimal(4),
        )
    )
    bad_teacher = Teacher(
        canonical_name="Docente Risco",
        normalized_name=normalize_text("Docente Risco"),
    )
    good_teacher = Teacher(
        canonical_name="Docente Bom",
        normalized_name=normalize_text("Docente Bom"),
    )
    session.add_all(
        [
            term,
            import_file,
            batch,
            mandatory_subject,
            free_subject,
            completed_subject,
            course,
            bad_teacher,
            good_teacher,
        ]
    )
    session.flush()
    mandatory_section = Section(
        term=term,
        subject=mandatory_subject,
        first_seen_batch_id=batch.id,
        last_seen_batch_id=batch.id,
        code="NA1MAND001-23SA",
        campus="SA",
        shift="Noturno",
        total_seats=20,
        theory_hours=4,
        practice_hours=0,
    )
    mandatory_section.teachers.append(
        SectionTeacher(teacher=bad_teacher, role=TeacherRole.THEORY, position=1)
    )
    mandatory_section.meetings.append(
        SectionMeeting(
            weekday=4,
            start_time=time(19, 0),
            end_time=time(21, 0),
            campus="SA",
            frequency=MeetingFrequency.WEEKLY,
            meeting_type=MeetingType.THEORY,
        )
    )
    mandatory_section.course_links.append(SectionCourseOffering(course=course))
    free_section = Section(
        term=term,
        subject=free_subject,
        first_seen_batch_id=batch.id,
        last_seen_batch_id=batch.id,
        code="NA1FREE001-23SA",
        campus="SA",
        shift="Matutino",
        total_seats=20,
        theory_hours=4,
        practice_hours=0,
    )
    free_section.teachers.append(
        SectionTeacher(teacher=good_teacher, role=TeacherRole.THEORY, position=1)
    )
    free_section.meetings.append(
        SectionMeeting(
            weekday=0,
            start_time=time(8, 0),
            end_time=time(10, 0),
            campus="SA",
            frequency=MeetingFrequency.WEEKLY,
            meeting_type=MeetingType.THEORY,
        )
    )
    free_section.course_links.append(SectionCourseOffering(course=course))
    completed_section = Section(
        term=term,
        subject=completed_subject,
        first_seen_batch_id=batch.id,
        last_seen_batch_id=batch.id,
        code="NA1DONE001-23SA",
        campus="SA",
        shift="Noturno",
        total_seats=20,
    )
    student = StudentProfile(
        display_name="Aluno Ranking",
        admission_year=2026,
        admission_shift="Noturno",
        campus="SA",
        ca=Decimal("3.4"),
        accumulated_credits=Decimal(0),
        course_strategy=CourseStrategy.PRIMARY_COURSE,
    )
    student.courses.append(
        StudentCourse(
            course=course,
            curriculum_version=curriculum,
            is_primary=True,
            cp=Decimal("0.95"),
        )
    )
    student.completed_subjects.append(
        StudentCompletedSubject(subject=completed_subject, grade="A", credits=Decimal(4))
    )
    session.add_all(
        [
            mandatory_section,
            free_section,
            completed_section,
            student,
        ]
    )
    session.flush()

    _add_teacher_statistics(session, bad_teacher, "bad-next", {"F": 20}, now)
    _add_teacher_statistics(session, good_teacher, "good-next", {"A": 20}, now)
    sync_run = UfabcNextSyncRun(
        season=term.code,
        status=ExternalSyncStatus.COMPLETED,
        started_at=now,
        finished_at=now,
    )
    session.add(sync_run)
    session.flush()
    session.add_all(
        [
            UfabcNextComponentSnapshot(
                sync_run_id=sync_run.id,
                term_id=term.id,
                section_id=mandatory_section.id,
                subject_id=mandatory_subject.id,
                external_section_code=mandatory_section.code,
                seats=20,
                requests=100,
                enrolled_count=0,
                payload={},
            ),
            UfabcNextComponentSnapshot(
                sync_run_id=sync_run.id,
                term_id=term.id,
                section_id=free_section.id,
                subject_id=free_subject.id,
                external_section_code=free_section.code,
                seats=20,
                requests=0,
                enrolled_count=0,
                payload={},
            ),
        ]
    )
    session.commit()
    return student, mandatory_section, free_section


def _add_teacher_statistics(
    session: Session,
    teacher: Teacher,
    external_id: str,
    counts: dict[str, int],
    now: datetime,
) -> None:
    result = calculate_grade_statistics(
        counts,
        reference_rates={"A": 0.5, "F": 0.5},
        prior_weight=20,
    )
    session.add(
        TeacherStatistics(
            teacher_id=teacher.id,
            external_teacher_id=external_id,
            source_fetched_at=now,
            computed_at=now,
            **_statistics_values(result),
        )
    )


def _statistics_values(result: GradeStatisticsResult) -> dict[str, object]:
    return {
        "grade_counts": result.grade_counts,
        "sample_size": result.sample_size,
        "effective_sample_size": Decimal(str(result.effective_sample_size)),
        "raw_a_rate": Decimal(str(result.raw.a_rate)),
        "adjusted_a_rate": Decimal(str(result.adjusted.a_rate)),
        "raw_ab_rate": Decimal(str(result.raw.ab_rate)),
        "adjusted_ab_rate": Decimal(str(result.adjusted.ab_rate)),
        "raw_failure_rate": Decimal(str(result.raw.failure_rate)),
        "adjusted_failure_rate": Decimal(str(result.adjusted.failure_rate)),
        "raw_fo_rate": Decimal(str(result.raw.fo_rate)),
        "adjusted_fo_rate": Decimal(str(result.adjusted.fo_rate)),
        "raw_mean_grade": Decimal(str(result.raw.mean_grade)),
        "adjusted_mean_grade": Decimal(str(result.adjusted.mean_grade)),
        "confidence": result.confidence,
        "prior_weight": Decimal(str(result.prior_weight)),
        "reference_rates": result.reference_rates,
        "grade_weights": result.grade_weights,
    }
