# ruff: noqa: E501

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.students.history as history_module
from app.models.students import StudentHistoryImport
from app.schemas.curriculum import CurriculumImportRequest
from app.services.credit_limits import calculate_max_quarter_credits
from app.services.curriculum import CurriculumService
from app.students.history import (
    HistoryEntry,
    HistoryPdfParser,
    ParsedStudentHistory,
    StudentHistoryService,
)
from app.students.service import StudentService


def test_official_credit_limit_rounds_up() -> None:
    assert calculate_max_quarter_credits(Decimal("2.85")) == Decimal(26)
    assert calculate_max_quarter_credits(Decimal("3.3")) == Decimal(27)
    assert calculate_max_quarter_credits(Decimal("2")) == Decimal(24)


def test_history_parser_reads_split_codes_and_coefficients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_text = """
Historico Escolar                                    Data de Emissao: 15/07/2026 as 19:12
Nome: ALUNO                                                        Matricula: 11234567890
Curso: BACHARELADO EM CIENCIA E TECNOLOGIA                         Status Discente: ATIVO
Curriculo: BCT 2015-2017 - 2017.2        Modalidade: Presencial    Campus: SANTO ANDRE    Turno: N
Ano / Periodo Letivo Inicial: 2021.3
Coeficiente de Rendimento (CR)                                                              2.1643
Coeficiente de Aproveitamento (CA)                                                          2.85
Coeficiente de Progressao (CP)                                                              0.8211
Coeficiente de Afinidade (IK)                                                               0.7388
Componentes Curriculares Cursados/Cursando
 Ano/Periodo                           Componente Curricular                             Cred.   CH     CH     Turma     Conceito     Situacao                Docente(s)
   Letivo                                                                                               EXT
                      BIJ0207-                                                                                NB3BIJ0
   2021.3      OBR       15     BASES CONCEITUAIS DA ENERGIA                               2     24      0      207-         A          APR
                                                                                                                15SB
   2026.2      OL     ESTO01    METODOS EXPERIMENTAIS EM ENGENHARIA                        4     48      0     O017-         -          MATR
                      7-17                                                                                      17SA
Legenda
"""

    class FakePage:
        def extract_text(self, *, extraction_mode: str) -> str:
            assert extraction_mode == "layout"
            return page_text

    class FakeReader:
        is_encrypted = False
        pages = [FakePage()]

        def __init__(self, _: object) -> None:
            pass

    monkeypatch.setattr(history_module, "PdfReader", FakeReader)
    parsed = HistoryPdfParser().parse(b"%PDF-test")

    assert parsed.ra == "11234567890"
    assert parsed.ca == Decimal("2.85")
    assert parsed.course_code == "BCT"
    assert [entry.code for entry in parsed.entries] == ["BIJ0207-15", "ESTO017-17"]
    assert [entry.status for entry in parsed.entries] == ["APR", "MATR"]


def test_reimport_replaces_the_single_history_for_ra(session: Session) -> None:
    CurriculumService(session).import_curriculum(
        CurriculumImportRequest.model_validate(
            {
                "course": {"code": "BCT", "name": "Bacharelado em Ciencia e Tecnologia"},
                "version": "2015",
                "admission_year_start": 2015,
                "admission_year_end": 2022,
                "unlisted_subject_category": "free",
                "subjects": [],
            }
        )
    )
    first = ParsedStudentHistory(
        ra="11234567890",
        admission_year=2021,
        admission_shift="Noturno",
        campus="SA",
        course_code="BCT",
        curriculum_version="2015",
        cr=Decimal("2.1"),
        ca=Decimal("2.85"),
        cp=Decimal("0.82"),
        issued_at=datetime(2026, 7, 15, 19, 12, tzinfo=UTC),
        page_count=5,
        entries=(
            HistoryEntry(
                code="BIJ0207-15",
                name="Bases Conceituais da Energia",
                term="2021:3",
                status="APR",
                category="OBR",
                grade="A",
                credits=Decimal(2),
                hours=24,
                extension_hours=0,
            ),
            HistoryEntry(
                code="ESTO017-17",
                name="Metodos Experimentais em Engenharia",
                term="2026:2",
                status="MATR",
                category="OL",
                grade=None,
                credits=Decimal(4),
                hours=48,
                extension_hours=0,
            ),
        ),
        warnings=(),
    )
    service = StudentHistoryService(session)
    first_result = service.import_pdf(
        parsed=first,
        content=b"%PDF-first",
        original_filename="historico.pdf",
        student_id=None,
    )
    session.commit()

    profile = StudentService(session).get_student(first_result.profile.id)
    assert profile.ca == Decimal("2.8500")
    assert profile.max_quarter_credits == Decimal("26.00")
    assert len(profile.completed_subjects) == 1
    assert len(profile.in_progress_subjects) == 1

    replacement = replace(
        first,
        ca=Decimal("3.1"),
        entries=(
            HistoryEntry(
                code="BIK0102-15",
                name="Estrutura da Materia",
                term="2021:3",
                status="APR",
                category="OBR",
                grade="B",
                credits=Decimal(3),
                hours=36,
                extension_hours=0,
            ),
        ),
    )
    second_result = service.import_pdf(
        parsed=replacement,
        content=b"%PDF-second",
        original_filename="historico-atualizado.pdf",
        student_id=profile.id,
    )
    session.commit()

    reloaded = StudentService(session).get_student(profile.id)
    assert second_result.replaced_existing is True
    assert reloaded.max_quarter_credits == Decimal("27.00")
    assert [item.subject.code for item in reloaded.completed_subjects] == ["BIK0102-15"]
    assert reloaded.in_progress_subjects == []
    assert session.scalar(select(func.count()).select_from(StudentHistoryImport)) == 1
