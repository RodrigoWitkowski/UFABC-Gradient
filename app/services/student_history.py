import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zoneinfo import ZoneInfo

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import Course, CurriculumVersion
from app.models.students import (
    StudentCompletedSubject,
    StudentCourse,
    StudentHistoryImport,
    StudentInProgressSubject,
    StudentPreference,
    StudentProfile,
)
from app.services.credit_limits import calculate_max_quarter_credits
from app.services.normalization.text import clean_text, normalize_code, strip_accents
from app.services.students import StudentService

PARSER_VERSION = "sigaa-history-v2"
MAX_HISTORY_PDF_BYTES = 10 * 1024 * 1024
ROW_RE = re.compile(r"^\s*(20\d{2}\.[1-3])\s")
ROW_CONTENT_RE = re.compile(
    r"^\s*(20\d{2}\.[1-3])\s+(?:(OBR|OL|LIV)\s+)?(\S+)\s{2,}(.*)$"
)
SUBJECT_CODE_RE = re.compile(r"^[A-Z]{2,5}\d{3,4}-\d{2}$")
CODE_FRAGMENT_RE = re.compile(r"([A-Z0-9-]*\d[A-Z0-9-]*)\s*$")
COMPLETED_STATUSES = {"APR", "APRN", "DISP", "TRANS", "INCORP", "CUMP"}
KNOWN_STATUSES = COMPLETED_STATUSES | {
    "CANC",
    "MATR",
    "REC",
    "REP",
    "REPF",
    "REPMF",
    "REPN",
    "REPNF",
    "TRANC",
}


class HistoryPdfError(ValueError):
    pass


class StudentHistoryConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    code: str
    name: str
    term: str | None
    status: str
    category: str | None
    grade: str | None
    credits: Decimal | None
    hours: int | None
    extension_hours: int | None
    equivalent_source_code: str | None = None

    def as_json(self) -> dict[str, str | int | None]:
        return {
            "code": self.code,
            "name": self.name,
            "term": self.term,
            "status": self.status,
            "category": self.category,
            "grade": self.grade,
            "credits": str(self.credits) if self.credits is not None else None,
            "hours": self.hours,
            "extension_hours": self.extension_hours,
            "equivalent_source_code": self.equivalent_source_code,
        }


@dataclass(frozen=True, slots=True)
class ParsedStudentHistory:
    ra: str
    admission_year: int
    admission_shift: str | None
    campus: str | None
    course_code: str | None
    curriculum_version: str | None
    cr: Decimal | None
    ca: Decimal
    cp: Decimal | None
    issued_at: datetime | None
    page_count: int
    entries: tuple[HistoryEntry, ...]
    warnings: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "ra": self.ra,
            "admission_year": self.admission_year,
            "admission_shift": self.admission_shift,
            "campus": self.campus,
            "course_code": self.course_code,
            "curriculum_version": self.curriculum_version,
            "cr": str(self.cr) if self.cr is not None else None,
            "ca": str(self.ca),
            "cp": str(self.cp) if self.cp is not None else None,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "entries": [entry.as_json() for entry in self.entries],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ParsedHistoryMetadata:
    ra: str
    admission_year: int
    admission_shift: str | None
    campus: str | None
    course_code: str | None
    curriculum_version: str | None
    cr: Decimal | None
    ca: Decimal
    cp: Decimal | None
    issued_at: datetime | None


@dataclass(frozen=True, slots=True)
class HistoryImportResult:
    profile: StudentProfile
    history_import: StudentHistoryImport
    replaced_existing: bool
    completed_count: int
    completed_attempt_count: int
    in_progress_count: int
    ignored_attempt_count: int
    warnings: list[str]


class HistoryPdfParser:
    def parse(self, content: bytes) -> ParsedStudentHistory:
        if not content.startswith(b"%PDF"):
            raise HistoryPdfError("o arquivo enviado nao e um PDF valido")
        if len(content) > MAX_HISTORY_PDF_BYTES:
            raise HistoryPdfError("o historico deve ter no maximo 10 MB")
        try:
            reader = PdfReader(BytesIO(content))
        except PdfReadError as exc:
            raise HistoryPdfError("nao foi possivel ler o PDF") from exc
        if reader.is_encrypted:
            raise HistoryPdfError("o PDF do historico nao pode estar protegido por senha")

        pages = [page.extract_text(extraction_mode="layout") or "" for page in reader.pages]
        if not any("Historico Escolar" in strip_accents(page) for page in pages):
            raise HistoryPdfError("o arquivo nao parece ser um Historico Escolar do SIGAA")

        metadata = self._parse_metadata("\n".join(pages))
        entries, warnings = self._parse_entries(pages)
        entries.extend(self._parse_convalidations(pages, entries))
        if not entries:
            raise HistoryPdfError("nenhuma disciplina foi identificada no historico")
        return ParsedStudentHistory(
            ra=metadata.ra,
            admission_year=metadata.admission_year,
            admission_shift=metadata.admission_shift,
            campus=metadata.campus,
            course_code=metadata.course_code,
            curriculum_version=metadata.curriculum_version,
            cr=metadata.cr,
            ca=metadata.ca,
            cp=metadata.cp,
            issued_at=metadata.issued_at,
            page_count=len(reader.pages),
            entries=tuple(entries),
            warnings=tuple(warnings),
        )

    def _parse_metadata(self, text: str) -> ParsedHistoryMetadata:
        normalized = strip_accents(text)
        ra_match = re.search(r"Matricula:\s*(\d{8,16})", normalized)
        initial_match = re.search(
            r"Ano\s*/\s*Periodo Letivo Inicial:\s*(20\d{2})\.[1-3]", normalized
        )
        ca = self._coefficient(normalized, "CA")
        if ra_match is None:
            raise HistoryPdfError("RA nao encontrado no historico")
        if initial_match is None:
            raise HistoryPdfError("ano de ingresso nao encontrado no historico")
        if ca is None:
            raise HistoryPdfError("CA nao encontrado no historico")

        course_line = self._line_value(normalized, "Curso:", "Status")
        curriculum_line = self._line_value(normalized, "Curriculo:", "Modalidade:")
        campus_match = re.search(r"Campus:\s*(.+?)\s+Turno:\s*([^\s]+)", normalized)
        issued_match = re.search(
            r"Data de Emissao:\s*(\d{2}/\d{2}/\d{4})\s+as\s+(\d{2}:\d{2})",
            normalized,
        )

        course_code = self._course_code(course_line, curriculum_line)
        version_match = re.search(r"\b(20\d{2})\b", curriculum_line or "")
        issued_at = None
        if issued_match:
            issued_at = datetime.strptime(
                f"{issued_match.group(1)} {issued_match.group(2)}", "%d/%m/%Y %H:%M"
            ).replace(tzinfo=ZoneInfo("America/Sao_Paulo"))

        campus = None
        admission_shift = None
        if campus_match:
            campus_text = campus_match.group(1).strip().upper()
            campus = "SB" if "BERNARDO" in campus_text else "SA" if "ANDRE" in campus_text else None
            shift_text = campus_match.group(2).strip().upper()
            admission_shift = (
                "Noturno"
                if shift_text in {"N", "NOTURNO"}
                else "Matutino"
                if shift_text in {"M", "MATUTINO"}
                else None
            )

        return ParsedHistoryMetadata(
            ra=ra_match.group(1),
            admission_year=int(initial_match.group(1)),
            admission_shift=admission_shift,
            campus=campus,
            course_code=course_code,
            curriculum_version=version_match.group(1) if version_match else None,
            cr=self._coefficient(normalized, "CR"),
            ca=ca,
            cp=self._coefficient(normalized, "CP"),
            issued_at=issued_at,
        )

    def _parse_entries(self, pages: list[str]) -> tuple[list[HistoryEntry], list[str]]:
        entries: list[HistoryEntry] = []
        warnings: list[str] = []
        for page_number, page in enumerate(pages, start=1):
            lines = page.splitlines()
            header_index = next(
                (
                    index
                    for index, line in enumerate(lines)
                    if "Componente Curricular" in line and "Cred." in line
                ),
                None,
            )
            if header_index is None:
                continue
            header = lines[header_index]
            credits_start = header.find("Cred.")
            table_end = next(
                (
                    index
                    for index in range(header_index + 1, len(lines))
                    if "Legenda" in lines[index] or "Para verificar a autenticidade" in lines[index]
                ),
                len(lines),
            )
            row_indexes = [
                index
                for index in range(header_index + 1, table_end)
                if ROW_RE.match(lines[index])
            ]
            for position, row_index in enumerate(row_indexes):
                next_row = (
                    row_indexes[position + 1]
                    if position + 1 < len(row_indexes)
                    else table_end
                )
                entry = self._parse_row(
                    lines=lines,
                    row_index=row_index,
                    block_end=max(row_index + 1, next_row - 1),
                    credits_start=credits_start,
                )
                if entry is not None:
                    entries.append(entry)
                elif "ENADE" not in lines[row_index]:
                    warnings.append(
                        f"pagina {page_number}: uma linha de disciplina nao pode ser validada"
                    )
        return entries, warnings

    def _parse_row(
        self,
        *,
        lines: list[str],
        row_index: int,
        block_end: int,
        credits_start: int,
    ) -> HistoryEntry | None:
        row = lines[row_index]
        previous = lines[row_index - 1] if row_index > 0 else ""
        next_line = lines[row_index + 1] if row_index + 1 < len(lines) else ""
        content_match = ROW_CONTENT_RE.match(row[:credits_start].rstrip())
        if content_match is None:
            return None
        category = content_match.group(2)
        row_fragment = content_match.group(3)
        name_start = content_match.start(4)
        previous_match = CODE_FRAGMENT_RE.search(previous[:name_start])
        next_match = CODE_FRAGMENT_RE.search(next_line[:name_start])
        fragments = [
            row_fragment,
            f"{previous_match.group(1) if previous_match else ''}{row_fragment}",
            f"{row_fragment}{next_match.group(1) if next_match else ''}",
        ]
        code = next(
            (
                normalized
                for candidate in fragments
                if (normalized := normalize_code(candidate)) is not None
                and SUBJECT_CODE_RE.fullmatch(normalized) is not None
            ),
            None,
        )
        if code is None:
            return None

        right_tokens = row[credits_start:].split()
        if len(right_tokens) < 6:
            return None
        try:
            credits = Decimal(right_tokens[0])
            hours = int(right_tokens[1])
            extension_hours = int(right_tokens[2])
        except (InvalidOperation, ValueError):
            return None
        grade = right_tokens[4]
        status = right_tokens[5].upper()
        if status not in KNOWN_STATUSES:
            return None

        name_parts: list[str] = []
        for line_index in range(row_index - 1, block_end):
            line = lines[line_index]
            if "Para verificar a autenticidade" in line:
                continue
            part = clean_text(line[name_start:credits_start])
            if part:
                name_parts.append(part)
        name = clean_text(" ".join(name_parts)) or code
        return HistoryEntry(
            code=code,
            name=name,
            term=content_match.group(1).replace(".", ":"),
            status=status,
            category=category,
            grade=None if grade in {"-", "---"} else grade,
            credits=credits,
            hours=hours,
            extension_hours=extension_hours,
        )

    def _parse_convalidations(
        self, pages: list[str], existing: list[HistoryEntry]
    ) -> list[HistoryEntry]:
        normalized = strip_accents("\n".join(pages))
        pattern = re.compile(
            r"Cumpriu\s+([A-Z]{2,5}\d{3,4}-\d{2})\s+-\s+(.+?)\s+"
            r"\(\d+\s*h\)\s+atraves de\s+([A-Z]{2,5}\d{3,4}-\d{2})",
            re.IGNORECASE,
        )
        known_codes = {entry.code for entry in existing if entry.status in COMPLETED_STATUSES}
        results: list[HistoryEntry] = []
        for match in pattern.finditer(normalized):
            code = match.group(1).upper()
            if code in known_codes:
                continue
            results.append(
                HistoryEntry(
                    code=code,
                    name=clean_text(match.group(2)) or code,
                    term=None,
                    status="CUMP",
                    category=None,
                    grade=None,
                    credits=None,
                    hours=None,
                    extension_hours=None,
                    equivalent_source_code=match.group(3).upper(),
                )
            )
        return results

    @staticmethod
    def _coefficient(text: str, code: str) -> Decimal | None:
        match = re.search(
            rf"Coeficiente de [^\n]*\({code}\)\s+([0-4](?:[.,]\d+)?)", text
        )
        return Decimal(match.group(1).replace(",", ".")) if match else None

    @staticmethod
    def _line_value(text: str, start: str, end: str) -> str | None:
        match = re.search(rf"{re.escape(start)}\s*(.+?)\s+{re.escape(end)}", text)
        return clean_text(match.group(1)) if match else None

    @staticmethod
    def _course_code(course: str | None, curriculum: str | None) -> str | None:
        curriculum_text = (curriculum or "").upper().replace("&", "")
        for code in ("BCC", "BCH", "BCT"):
            if re.search(rf"\b{code}\b", curriculum_text):
                return code
        course_text = (course or "").upper()
        if "COMPUTACAO" in course_text:
            return "BCC"
        if "HUMANIDADES" in course_text:
            return "BCH"
        if "CIENCIA E TECNOLOGIA" in course_text:
            return "BCT"
        return None


class StudentHistoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentService(session)

    def import_pdf(
        self,
        *,
        parsed: ParsedStudentHistory,
        content: bytes,
        original_filename: str,
        student_id: uuid.UUID | None,
    ) -> HistoryImportResult:
        profile = self._resolve_profile(parsed, student_id)
        profile.ra = parsed.ra
        profile.admission_year = parsed.admission_year
        profile.admission_shift = parsed.admission_shift
        profile.campus = parsed.campus
        profile.cr = parsed.cr
        profile.ca = parsed.ca
        profile.max_quarter_credits = calculate_max_quarter_credits(parsed.ca)

        warnings = list(parsed.warnings)
        self._apply_course(profile, parsed, warnings)
        completed_count, completed_attempt_count, in_progress_count, ignored_count = (
            self._replace_subjects(profile, parsed)
        )

        imported_at = datetime.now(UTC)
        history_import = profile.history_import
        replaced_existing = history_import is not None
        if history_import is None:
            history_import = StudentHistoryImport(
                student_profile=profile,
                ra=parsed.ra,
                original_filename=original_filename,
                sha256="",
                parser_version=PARSER_VERSION,
                page_count=parsed.page_count,
                issued_at=parsed.issued_at,
                imported_at=imported_at,
                extracted_data={},
            )
            profile.history_import = history_import
            self.session.add(history_import)
        history_import.ra = parsed.ra
        history_import.original_filename = original_filename[:255]
        history_import.sha256 = hashlib.sha256(content).hexdigest()
        history_import.parser_version = PARSER_VERSION
        history_import.page_count = parsed.page_count
        history_import.issued_at = parsed.issued_at
        history_import.imported_at = imported_at
        history_import.extracted_data = parsed.as_json()
        self.session.flush()
        return HistoryImportResult(
            profile=profile,
            history_import=history_import,
            replaced_existing=replaced_existing,
            completed_count=completed_count,
            completed_attempt_count=completed_attempt_count,
            in_progress_count=in_progress_count,
            ignored_attempt_count=ignored_count,
            warnings=warnings,
        )

    def _resolve_profile(
        self, parsed: ParsedStudentHistory, student_id: uuid.UUID | None
    ) -> StudentProfile:
        profile = self.students.get_student(student_id) if student_id else None
        profile_for_ra = self.session.scalar(
            select(StudentProfile).where(StudentProfile.ra == parsed.ra)
        )
        if profile is not None and profile.ra not in {None, parsed.ra}:
            raise StudentHistoryConflictError("o RA do PDF difere do RA deste perfil")
        if profile is not None and profile_for_ra is not None and profile_for_ra.id != profile.id:
            raise StudentHistoryConflictError("este RA ja pertence a outro perfil")
        if profile is None and profile_for_ra is not None:
            return self.students.get_student(profile_for_ra.id)
        if profile is not None:
            return profile

        profile = StudentProfile(
            ra=parsed.ra,
            admission_year=parsed.admission_year,
            admission_shift=parsed.admission_shift,
            campus=parsed.campus,
            cr=parsed.cr,
            ca=parsed.ca,
            max_quarter_credits=calculate_max_quarter_credits(parsed.ca),
            accumulated_credits=Decimal(0),
            preferences=StudentPreference(hard_constraints={}, soft_preferences={}),
        )
        self.session.add(profile)
        self.session.flush()
        return profile

    def _apply_course(
        self,
        profile: StudentProfile,
        parsed: ParsedStudentHistory,
        warnings: list[str],
    ) -> None:
        if parsed.course_code is None:
            warnings.append("curso do historico nao foi reconhecido automaticamente")
            return
        course = self.session.scalar(select(Course).where(Course.code == parsed.course_code))
        if course is None:
            warnings.append(f"curso {parsed.course_code} ainda nao existe no banco")
            return
        student_course = next(
            (item for item in profile.courses if item.course_id == course.id), None
        )
        if student_course is None:
            curriculum = None
            if parsed.curriculum_version:
                curriculum = self.session.scalar(
                    select(CurriculumVersion).where(
                        CurriculumVersion.course_id == course.id,
                        CurriculumVersion.version == parsed.curriculum_version,
                    )
                )
            curriculum = curriculum or self.students._resolve_curriculum(  # noqa: SLF001
                course=course,
                version=None,
                admission_year=parsed.admission_year,
            )
            student_course = StudentCourse(
                course=course,
                curriculum_version=curriculum,
                is_primary=not profile.courses,
            )
            profile.courses.append(student_course)
        student_course.cp = parsed.cp

    def _replace_subjects(
        self, profile: StudentProfile, parsed: ParsedStudentHistory
    ) -> tuple[int, int, int, int]:
        completed: dict[str, HistoryEntry] = {}
        in_progress: dict[str, HistoryEntry] = {}
        ignored_count = 0
        completed_attempt_count = 0
        for entry in parsed.entries:
            if entry.status in COMPLETED_STATUSES:
                completed_attempt_count += 1
                completed[entry.code] = entry
            elif entry.status == "MATR":
                in_progress[entry.code] = entry
            else:
                ignored_count += 1
        for code in completed:
            in_progress.pop(code, None)

        profile.completed_subjects.clear()
        profile.in_progress_subjects.clear()
        self.session.flush()
        total_credits = Decimal(0)
        for entry in completed.values():
            subject = self.students._resolve_subject(entry.code, entry.name)  # noqa: SLF001
            credits = entry.credits
            total_credits += credits or Decimal(0)
            profile.completed_subjects.append(
                StudentCompletedSubject(
                    subject=subject,
                    term=self.students._resolve_term(entry.term),  # noqa: SLF001
                    grade=entry.grade,
                    credits=credits,
                    metadata_={
                        "source": "sigaa_history_pdf",
                        "status": entry.status,
                        "category": entry.category,
                        "hours": entry.hours,
                        "extension_hours": entry.extension_hours,
                        "equivalent_source_code": entry.equivalent_source_code,
                    },
                )
            )
        for entry in in_progress.values():
            subject = self.students._resolve_subject(entry.code, entry.name)  # noqa: SLF001
            profile.in_progress_subjects.append(
                StudentInProgressSubject(
                    subject=subject,
                    term=self.students._resolve_term(entry.term),  # noqa: SLF001
                )
            )
        profile.accumulated_credits = total_credits
        return len(completed), completed_attempt_count, len(in_progress), ignored_count
