import json
from collections.abc import Generator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db
from app.main import app
from app.models.enums import ExternalSyncStatus, ImportStatus, TeacherRole
from app.models.imports import ImportBatch, ImportFile, Term
from app.models.offerings import Section, SectionTeacher, Subject, Teacher, TeacherAlias
from app.models.ufabc_next import (
    ExternalSubjectIdentifier,
    SubjectReviewSnapshot,
    TeacherReviewSnapshot,
    UfabcNextCacheEntry,
    UfabcNextComponentSnapshot,
    UfabcNextSyncRun,
)
from app.schemas.ufabc_next import UfabcNextSyncRequest
from app.services.normalization.text import normalize_text
from app.services.ufabc_next.cache import UfabcNextDatabaseCache
from app.services.ufabc_next.client import (
    UfabcNextClient,
    UfabcNextRateLimitError,
    UfabcNextRequestLimitError,
)
from app.services.ufabc_next.sync import UfabcNextSyncError, UfabcNextSyncService


@pytest.fixture
def api_client(session: Session) -> Generator[TestClient, None, None]:
    def override_database() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_database
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def next_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ufabc_next_base_url": "https://next.test",
        "ufabc_next_timeout_seconds": 1,
        "ufabc_next_max_retries": 1,
        "ufabc_next_backoff_seconds": 0,
        "ufabc_next_min_interval_seconds": 0,
        "ufabc_next_component_cache_seconds": 900,
        "ufabc_next_review_cache_seconds": 900,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def create_offering(session: Session) -> tuple[Term, Section, Teacher]:
    term = Term(code="2026:3", year=2026, term_number=3)
    import_file = ImportFile(
        original_filename="offer.csv",
        stored_path="var/offer.csv",
        sha256="a" * 64,
        size_bytes=1,
        content_type="text/csv",
    )
    batch = ImportBatch(
        import_file=import_file,
        term=term,
        status=ImportStatus.COMPLETED,
        parser_config={},
    )
    session.add_all([term, import_file, batch])
    session.flush()

    subject = Subject(code="TEST001-23", name="Teste", normalized_name=normalize_text("Teste"))
    teacher = Teacher(
        canonical_name="Docente Teste",
        normalized_name=normalize_text("Docente Teste"),
    )
    teacher.aliases.append(
        TeacherAlias(
            name="Docente Teste",
            normalized_name=normalize_text("Docente Teste"),
        )
    )
    section = Section(
        term=term,
        subject=subject,
        first_seen_batch_id=batch.id,
        last_seen_batch_id=batch.id,
        code="NA1TEST001-23SA",
        total_seats=40,
    )
    section.teachers.append(
        SectionTeacher(teacher=teacher, role=TeacherRole.THEORY, position=1)
    )
    session.add_all([subject, teacher, section])
    session.commit()
    return term, section, teacher


def components_payload() -> list[dict[str, object]]:
    common = {
        "codigo": "TEST001-23",
        "subject": "Teste",
        "season": "2026:3",
        "subjectId": "subject-next-1",
        "vagas": 40,
        "requisicoes": 25,
        "ideal_quad": False,
        "campus": "sa",
        "turno": "noturno",
    }
    return [
        {
            **common,
            "disciplina_id": 10,
            "uf_cod_turma": "NA1TEST001-23SA",
            "turma": "A1",
            "teoria": "Docente Teste",
            "teoriaId": "teacher-next-1",
            "alunos_matriculados": [{"studentId": 123, "login": "private"}],
        },
        {
            **common,
            "disciplina_id": 11,
            "uf_cod_turma": "NA2TEST001-23SA",
            "turma": "A2",
            "alunos_matriculados": [],
        },
    ]


def review_payload() -> dict[str, object]:
    return {
        "teacher": {
            "_id": "teacher-next-1",
            "name": "Docente Teste",
            "siape": "private",
            "externalKey": "private",
        },
        "general": {
            "count": 3,
            "amount": 3,
            "cr_professor": 3.0,
            "distribution": [
                {"conceito": "A", "count": 2},
                {"conceito": "C", "count": 1},
            ],
        },
        "specific": [
            {
                "count": 3,
                "teacher": {"_id": "teacher-next-1", "siape": "private"},
            }
        ],
    }


def build_mock_client(
    session: Session,
    handler: httpx.MockTransport,
    **settings_overrides: object,
) -> UfabcNextClient:
    http_client = httpx.Client(base_url="https://next.test", transport=handler)
    return UfabcNextClient(
        next_settings(**settings_overrides),
        UfabcNextDatabaseCache(session),
        http_client=http_client,
    )


def test_client_retries_and_uses_sanitized_cache(session: Session) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"message": "temporary"})
        return httpx.Response(200, json=components_payload())

    client = build_mock_client(session, httpx.MockTransport(handler))
    first = client.get_components("2026:3")
    second = client.get_components("2026:3")

    assert calls == 2
    assert client.remote_requests == 2
    assert client.cache_hits == 1
    assert first == second
    assert first[0]["enrolled_count"] == 1
    assert "alunos_matriculados" not in first[0]
    cached = session.scalar(select(UfabcNextCacheEntry))
    assert cached is not None
    assert "private" not in json.dumps(cached.response_body)


def test_client_stops_at_local_remote_request_limit(session: Session) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=components_payload())

    client = build_mock_client(
        session,
        httpx.MockTransport(handler),
        ufabc_next_max_requests_per_sync=1,
    )
    client.get_components("2026:3")

    with pytest.raises(UfabcNextRequestLimitError, match="limite local"):
        client.get_teacher_reviews("teacher-next-1")

    assert calls == 1
    assert client.remote_requests == 1


def test_client_stops_immediately_on_remote_rate_limit(session: Session) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={
                "retry-after": "45",
                "x-ratelimit-limit": "1000",
                "x-ratelimit-remaining": "0",
            },
            json={"message": "slow down"},
        )

    client = build_mock_client(
        session,
        httpx.MockTransport(handler),
        ufabc_next_max_retries=2,
    )

    with pytest.raises(UfabcNextRateLimitError, match="429"):
        client.get_components("2026:3")

    assert calls == 1
    assert client.request_log == [
        {
            "path": "/entities/components",
            "status_code": 429,
            "x_ratelimit_limit": "1000",
            "x_ratelimit_remaining": "0",
            "retry_after": "45",
        }
    ]


def test_sync_persists_components_reviews_and_external_links(session: Session) -> None:
    _, section, teacher = create_offering(session)
    alternate_subject = Subject(
        code="ALT001-23",
        name="Teste alternativo",
        normalized_name=normalize_text("Teste alternativo"),
    )
    session.add(alternate_subject)
    session.commit()
    component_response = components_payload()
    component_response[1]["codigo"] = "ALT001-23"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/entities/components":
            return httpx.Response(200, json=component_response)
        if request.url.path.startswith("/entities/teachers/reviews/"):
            return httpx.Response(200, json=review_payload())
        if request.url.path.startswith("/entities/subjects/reviews/"):
            return httpx.Response(200, json=review_payload())
        return httpx.Response(404, json={"message": "not found"})

    client = build_mock_client(session, httpx.MockTransport(handler))
    run = UfabcNextSyncService(session, client).sync(
        UfabcNextSyncRequest(
            season="2026:3",
            include_teacher_reviews=True,
            include_subject_reviews=True,
            review_limit=10,
        )
    )

    assert run.status == ExternalSyncStatus.COMPLETED_WITH_WARNINGS
    assert run.components_received == 2
    assert run.components_matched == 1
    assert run.components_unmatched == 1
    assert run.teacher_reviews_synced == 1
    assert run.subject_reviews_synced == 1
    assert run.remote_requests == 3

    snapshots = session.scalars(select(UfabcNextComponentSnapshot)).all()
    assert len(snapshots) == 2
    matched = next(item for item in snapshots if item.section_id is not None)
    assert matched.section_id == section.id
    assert matched.enrolled_count == 1
    assert "alunos_matriculados" not in matched.payload

    teacher_review = session.scalar(select(TeacherReviewSnapshot))
    subject_review = session.scalar(select(SubjectReviewSnapshot))
    assert teacher_review is not None
    assert subject_review is not None
    assert teacher_review.teacher_id == teacher.id
    assert teacher_review.sample_size == 3
    assert subject_review.subject_id is None
    assert (
        session.scalar(select(func.count()).select_from(ExternalSubjectIdentifier)) == 2
    )
    persisted_reviews = json.dumps(
        [
            teacher_review.metrics,
            teacher_review.distribution,
            teacher_review.specific_statistics,
            subject_review.teacher_statistics,
        ]
    )
    assert "siape" not in persisted_reviews
    assert "externalKey" not in persisted_reviews


def test_sync_start_is_not_exposed_and_status_is_read_only(
    api_client: TestClient,
    session: Session,
) -> None:
    create_offering(session)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/entities/components"
        return httpx.Response(200, json=components_payload()[:1])

    mock_client = build_mock_client(session, httpx.MockTransport(handler))
    run = UfabcNextSyncService(session, mock_client).sync(
        UfabcNextSyncRequest(season="2026:3")
    )

    response = api_client.post("/sync/ufabc-next", json={"season": "2026:3"})
    assert response.status_code == 404
    status_response = api_client.get(
        "/admin/integrations/ufabc-next/status",
        params={"run_id": str(run.id)},
    )
    assert status_response.status_code == 200
    assert status_response.json()["id"] == str(run.id)
    assert session.scalar(select(func.count()).select_from(UfabcNextSyncRun)) == 1


def test_sync_batches_advance_to_teachers_without_snapshots(session: Session) -> None:
    create_offering(session)
    component_response = components_payload()
    component_response[1]["teoria"] = "Docente Teste"
    component_response[1]["teoriaId"] = "teacher-next-2"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/entities/components":
            return httpx.Response(200, json=component_response)
        if request.url.path.startswith("/entities/teachers/reviews/"):
            return httpx.Response(200, json=review_payload())
        return httpx.Response(404)

    first_client = build_mock_client(session, httpx.MockTransport(handler))
    first_service = UfabcNextSyncService(session, first_client)
    first_service.sync(
        UfabcNextSyncRequest(
            season="2026:3",
            include_teacher_reviews=True,
            review_limit=1,
        )
    )

    second_client = build_mock_client(session, httpx.MockTransport(handler))
    second_service = UfabcNextSyncService(session, second_client)
    second_service.sync(
        UfabcNextSyncRequest(
            season="2026:3",
            include_teacher_reviews=True,
            review_limit=1,
        )
    )

    reviewed = set(session.scalars(select(TeacherReviewSnapshot.external_teacher_id)).all())
    assert reviewed == {"teacher-next-1", "teacher-next-2"}
    assert session.scalar(select(func.count()).select_from(UfabcNextComponentSnapshot)) == 2
    assert second_service.review_progress()["teacher_pending"] == 0


def test_sync_rejects_another_active_run(session: Session) -> None:
    create_offering(session)
    active = UfabcNextSyncRun(
        season="2026:3",
        status=ExternalSyncStatus.RUNNING,
        started_at=datetime.now(UTC).replace(tzinfo=None),
        warnings=[],
        request_log=[],
    )
    session.add(active)
    session.commit()
    client = build_mock_client(
        session,
        httpx.MockTransport(lambda _: httpx.Response(500)),
    )

    with pytest.raises(ValueError, match="sincronizacao em andamento"):
        UfabcNextSyncService(session, client).sync(UfabcNextSyncRequest(season="2026:3"))

    assert client.remote_requests == 0


def test_failed_sync_is_persisted(session: Session) -> None:
    create_offering(session)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "temporary"})

    client = build_mock_client(
        session,
        httpx.MockTransport(handler),
        ufabc_next_max_retries=0,
    )

    with pytest.raises(UfabcNextSyncError) as caught:
        UfabcNextSyncService(session, client).sync(UfabcNextSyncRequest(season="2026:3"))

    run = session.get(UfabcNextSyncRun, caught.value.run_id)
    assert run is not None
    assert run.status == ExternalSyncStatus.FAILED
    assert run.remote_requests == 1
    assert run.request_log[0]["status_code"] == 503
    assert "HTTP 503" in (run.error_message or "")
