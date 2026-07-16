from dataclasses import dataclass
from typing import Any

from app.services.normalization.text import normalize_header

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "course_name": ("curso",),
    "section_code": ("codigo turma", "codigo de turma", "codigo"),
    "section_display_name": ("disciplina turma turno campus",),
    "subject_name": ("disciplina", "nome disciplina"),
    "subject_code": ("codigo disciplina",),
    "class_group": ("turma",),
    "theory_schedule": ("horario teoria", "teoria com sala"),
    "practice_schedule": ("horario pratica", "pratica com sala"),
    "campus": ("campus",),
    "shift": ("turno",),
    "workload": ("tpi", "tpei"),
    "total_seats": ("vagas", "vagas totais"),
    "reserved_seats": ("reserva", "vagas ingressantes"),
    "teacher_theory_name_1": ("docente teoria",),
    "teacher_theory_id_1": ("siape docente teoria",),
    "teacher_theory_name_2": ("docente teoria 2",),
    "teacher_theory_id_2": ("siape docente teoria 2",),
    "teacher_theory_name_3": ("docente teoria 3",),
    "teacher_theory_id_3": ("siape docente teoria 3",),
    "teacher_practice_name_1": ("docente pratica",),
    "teacher_practice_id_1": ("siape docente pratica",),
    "teacher_practice_name_2": ("docente pratica 2",),
    "teacher_practice_id_2": ("siape docente pratica 2",),
    "teacher_practice_name_3": ("docente pratica 3",),
    "teacher_practice_id_3": ("siape docente pratica 3",),
}
REQUIRED_COLUMNS = {"section_code", "subject_code", "subject_name"}


@dataclass(frozen=True, slots=True)
class ResolvedColumnMapping:
    columns: dict[str, str]

    def get(self, row: dict[str, Any], canonical_name: str) -> Any:
        actual = self.columns.get(canonical_name)
        return row.get(actual) if actual else None


def resolve_column_mapping(
    headers: list[object],
    custom_mapping: dict[str, str] | None = None,
) -> ResolvedColumnMapping:
    actual_headers = [str(header) for header in headers]
    normalized_to_actual: dict[str, str] = {}
    for header in actual_headers:
        normalized_to_actual.setdefault(normalize_header(header), header)

    resolved: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        if custom_mapping and canonical in custom_mapping:
            requested = custom_mapping[canonical]
            if requested in actual_headers:
                resolved[canonical] = requested
                continue
            normalized_requested = normalize_header(requested)
            if normalized_requested in normalized_to_actual:
                resolved[canonical] = normalized_to_actual[normalized_requested]
                continue
            raise ValueError(f"coluna configurada nao encontrada: {requested}")

        for alias in aliases:
            actual = normalized_to_actual.get(alias)
            if actual is not None:
                resolved[canonical] = actual
                break

    missing = sorted(REQUIRED_COLUMNS - resolved.keys())
    if missing:
        raise ValueError(f"colunas obrigatorias ausentes: {', '.join(missing)}")
    return ResolvedColumnMapping(resolved)


def mapping_score(headers: list[object]) -> tuple[bool, int]:
    try:
        mapping = resolve_column_mapping(headers)
    except ValueError:
        return False, 0
    return True, len(mapping.columns)
