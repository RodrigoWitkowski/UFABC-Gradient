import shutil
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import ImportStatus, MeetingFrequency, TeacherRole
from app.models.imports import ImportFile, ImportIssue
from app.models.offerings import Section, SectionRevision
from app.services.imports import OfferImporter


def offer_row(**overrides: str) -> dict[str, str]:
    row = {
        "Curso": "BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO",
        "Código turma": "NA1MCCC001-23SA",
        "Disciplina Turma-Turno (Campus)": "ALGORITMOS A1-Noturno (SA)",
        "Disciplina": "ALGORITMOS",
        "Código disciplina": "MCCC001-23",
        "Turma": "A1",
        "Horário Teoria": "terça das 19:00 às 21:00, sala A-101, semanal",
        "Horário Prática": "quinta das 21:00 às 23:00, sala L-201, quinzenal I",
        "Campus": "SA",
        "Turno": "Noturno",
        "TPI": "2-2-4",
        "Vagas": "30",
        "Reserva": "5",
        "Docente Teoria": "JOÃO A. DA SILVA",
        "Siape Docente Teoria": "1234567",
        "Docente Prática": "João A da Silva",
        "Siape Docente Prática": "1234567",
    }
    row.update(overrides)
    return row


def write_workbook(path: Path, row: dict[str, str] | list[dict[str, str]]) -> None:
    rows = row if isinstance(row, list) else [row]
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"coluna auxiliar": ["ignorar"]}).to_excel(
            writer, sheet_name="Auxiliar", index=False
        )
        pd.DataFrame(rows).to_excel(writer, sheet_name=" turmas sistema atual", index=False)


def test_xlsx_import_normalizes_and_versions_sections(
    session: Session,
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "matriculas_2026_3.xlsx"
    write_workbook(workbook, offer_row())

    first = OfferImporter(session, tmp_path / "storage").import_path(workbook)

    assert first.status == ImportStatus.COMPLETED
    assert first.term is not None and first.term.code == "2026:3"
    assert first.source_sheet == " turmas sistema atual"
    assert first.imported_rows == 1
    assert first.added_sections == 1
    assert first.removed_sections == 0
    section = session.scalar(select(Section))
    assert section is not None
    assert section.subject.code == "MCCC001-23"
    assert section.total_seats == 30
    assert section.theory_hours == 2
    assert section.practice_hours == 2
    assert section.individual_hours == 4
    assert len(section.meetings) == 2
    assert {meeting.frequency for meeting in section.meetings} == {
        MeetingFrequency.WEEKLY,
        MeetingFrequency.BIWEEKLY_I,
    }
    assert len(section.teachers) == 2
    assert {item.role for item in section.teachers} == {
        TeacherRole.THEORY,
        TeacherRole.PRACTICE,
    }
    assert section.teachers[0].teacher.id == section.teachers[1].teacher.id

    write_workbook(
        workbook,
        offer_row(
            Vagas="45",
            **{"Horário Teoria": "terça das 19:00 às 21:00, sala A-102, semanal"},
        ),
    )
    second = OfferImporter(session, tmp_path / "storage").import_path(workbook)

    assert second.status == ImportStatus.COMPLETED
    assert second.changed_sections == 1
    assert second.added_sections == 0
    assert second.removed_sections == 0
    assert second.comparison_batch_id == first.id
    session.refresh(section)
    assert section.total_seats == 45
    revisions = session.scalars(
        select(SectionRevision).where(SectionRevision.section_id == section.id)
    ).all()
    assert len(revisions) == 2
    assert set(revisions[-1].changed_fields) == {"meetings", "total_seats"}
    assert session.scalar(select(func.count(ImportFile.id))) == 2

    renamed = tmp_path / "oferta_renomeada_2026_3.xlsx"
    shutil.copyfile(workbook, renamed)
    third = OfferImporter(session, tmp_path / "storage").import_path(renamed)
    assert third.changed_sections == 0
    assert session.scalar(select(func.count(ImportFile.id))) == 3


def test_csv_custom_column_mapping_and_invalid_row_reporting(
    session: Session,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "oferta.csv"
    pd.DataFrame(
        [
            {
                "cod_turma": "NA1TESTE-SA",
                "cod_disciplina": "TESTE-1",
                "nome": "DISCIPLINA TESTE",
                "horario": "segunda das 19:00 às 21:00, semanal",
            },
            {
                "cod_turma": "",
                "cod_disciplina": "TESTE-2",
                "nome": "LINHA INVÁLIDA",
                "horario": "quarta das 19:00 às 21:00, semanal",
            },
        ]
    ).to_csv(csv_path, index=False, encoding="utf-8-sig")

    batch = OfferImporter(session, tmp_path / "storage").import_path(
        csv_path,
        term_code="2026:3",
        column_mapping={
            "section_code": "cod_turma",
            "subject_code": "cod_disciplina",
            "subject_name": "nome",
            "theory_schedule": "horario",
        },
    )

    assert batch.status == ImportStatus.COMPLETED_WITH_ISSUES
    assert batch.imported_rows == 1
    assert batch.invalid_rows == 1
    issue = session.scalar(select(ImportIssue).where(ImportIssue.code == "section.missing_code"))
    assert issue is not None
    assert issue.code == "section.missing_code"
    assert issue.row_number == 3


def test_new_version_deactivates_sections_missing_from_offer(
    session: Session,
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "matriculas_2026_3.xlsx"
    second_row = offer_row(
        **{
            "Código turma": "NA2MCCC002-23SA",
            "Código disciplina": "MCCC002-23",
            "Disciplina": "ESTRUTURAS DE DADOS",
        }
    )
    write_workbook(workbook, [offer_row(), second_row])
    first = OfferImporter(session, tmp_path / "storage").import_path(workbook)
    assert first.added_sections == 2

    write_workbook(workbook, offer_row())
    second = OfferImporter(session, tmp_path / "storage").import_path(workbook)

    assert second.removed_sections == 1
    assert session.scalar(select(func.count(Section.id)).where(Section.is_active.is_(True))) == 1
