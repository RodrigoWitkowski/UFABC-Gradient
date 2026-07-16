import json
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.enums import CurriculumCategory
from app.schemas.curriculum import CurriculumImportRequest
from app.services.curriculum import CurriculumService


@pytest.fixture
def client(session: Session) -> Generator[TestClient, None, None]:
    def override_database() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_database
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_web_interface_and_assets_are_served(client: TestClient) -> None:
    page = client.get("/")
    stylesheet = client.get("/assets/styles.css")
    script = client.get("/assets/app.js")

    assert page.status_code == 200
    assert "Trajeto UFABC" in page.text
    assert 'id="ranking-form"' in page.text
    assert 'id="current-term"' in page.text
    assert 'id="period-window"' in page.text
    assert 'id="max-subject-credits"' not in page.text
    assert stylesheet.status_code == 200
    assert "--green:" in stylesheet.text
    assert script.status_code == 200
    assert 'fetchJson("/rankings/sections"' in script.text
    assert "compatibilidade" in script.text


def test_offer_import_and_status_endpoints(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "import_storage_path", tmp_path / "imports")
    csv_content = (
        "cod_turma,cod_disciplina,nome,horario\n"
        'NA1TESTE-SA,TESTE-1,DISCIPLINA TESTE,"segunda das 19:00 às 21:00, semanal"\n'
    ).encode()
    mapping = {
        "section_code": "cod_turma",
        "subject_code": "cod_disciplina",
        "subject_name": "nome",
        "theory_schedule": "horario",
    }

    response = client.post(
        "/imports/offers",
        files={"file": ("matriculas_2026_3.csv", csv_content, "text/csv")},
        data={"column_mapping": json.dumps(mapping)},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["term"] == "2026:3"
    assert payload["imported_rows"] == 1
    assert payload["invalid_rows"] == 0
    assert payload["added_sections"] == 1
    status_response = client.get(f"/imports/{payload['id']}")
    assert status_response.status_code == 200
    assert status_response.json()["sha256"] == payload["sha256"]

    sections_response = client.get("/terms/2026:3/sections")
    assert sections_response.status_code == 200
    assert sections_response.json()["total"] == 1


def test_curriculum_api_keeps_category_on_relationship(client: TestClient) -> None:
    response = client.post(
        "/curriculums/import",
        json={
            "course": {"code": "BCC", "name": "Bacharelado em Ciência da Computação"},
            "version": "2025",
            "subjects": [
                {
                    "code": "MCCC001-23",
                    "name": "Algoritmos",
                    "category": "mandatory",
                    "ideal_term": 3,
                    "credits": 4,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["subjects"][0]["category"] == "mandatory"
    course_id = payload["course"]["id"]
    list_response = client.get("/courses")
    assert list_response.status_code == 200
    assert list_response.json()[0]["curriculum_versions"][0]["version"] == "2025"
    get_response = client.get(f"/courses/{course_id}/curriculums/2025")
    assert get_response.status_code == 200
    assert get_response.json() == payload


def test_student_academic_profile_api(client: TestClient, session: Session) -> None:
    CurriculumService(session).import_curriculum(
        CurriculumImportRequest.model_validate(
            {
                "course": {
                    "code": "BCC",
                    "name": "Bacharelado em Ciência da Computação",
                },
                "version": "2025",
                "admission_year_start": 2025,
                "unlisted_subject_category": "free",
                "subjects": [
                    {
                        "code": "MCCC001-23",
                        "name": "Algoritmos",
                        "category": CurriculumCategory.MANDATORY,
                        "ideal_term": 3,
                        "credits": 4,
                    }
                ],
            }
        )
    )
    session.commit()
    create_response = client.post(
        "/students",
        json={
            "ra": "11234567890",
            "display_name": "Aluno de teste",
            "admission_year": 2025,
            "admission_shift": "Noturno",
        },
    )
    assert create_response.status_code == 201
    student_id = create_response.json()["id"]

    update_response = client.put(
        f"/students/{student_id}/academic-profile",
        json={
            "ra": "11234567890",
            "admission_year": 2025,
            "admission_shift": "Noturno",
            "cr": 3.1,
            "ca": 3.3,
            "max_quarter_credits": 27,
            "courses": [
                {
                    "course_code": "BCC",
                    "is_primary": True,
                    "cp": 0.38,
                    "ik": 0.41,
                }
            ],
            "completed_subjects": [],
            "in_progress_subjects": [{"code": "MCCC001-23", "term": "2026:3"}],
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["ra"] == "11234567890"
    assert update_response.json()["ca"] == "3.3"
    assert update_response.json()["max_quarter_credits"] == "27"
    assert update_response.json()["courses"][0]["curriculum_version"] == "2025"

    classification_response = client.get(
        f"/students/{student_id}/subjects/MCCC001-23/classifications"
    )
    assert classification_response.status_code == 200
    classification = classification_response.json()["classifications"][0]
    assert classification["course_code"] == "BCC"
    assert classification["category"] == "mandatory"
