import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.models.curriculum import Course
from app.models.enums import (
    ImportIssueLevel,
    ImportStatus,
    MeetingType,
    TeacherAliasStatus,
    TeacherRole,
)
from app.models.imports import ImportBatch, ImportFile, ImportIssue, Term
from app.models.offerings import (
    ExternalTeacherIdentifier,
    Section,
    SectionCourseOffering,
    SectionMeeting,
    SectionRevision,
    SectionTeacher,
    Subject,
    Teacher,
    TeacherAlias,
)
from app.services.imports.column_mapping import ResolvedColumnMapping, resolve_column_mapping
from app.services.imports.readers import read_offer_table
from app.services.imports.storage import ImportStorage, PreservedFile
from app.services.normalization.schedule import ParsedMeeting, parse_schedule
from app.services.normalization.text import (
    clean_text,
    generated_course_code,
    infer_term_code,
    normalize_code,
    normalize_term_code,
    normalize_text,
    parse_optional_int,
)

logger = logging.getLogger(__name__)
COMPLETED_STATUSES = (ImportStatus.COMPLETED, ImportStatus.COMPLETED_WITH_ISSUES)
PLACEHOLDER_TEACHERS = {"0a definir docente", "a definir docente", "docente a definir"}


class RowImportError(ValueError):
    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.field = field


class OfferImporter:
    def __init__(self, session: Session, storage_root: Path) -> None:
        self.session = session
        self.storage = ImportStorage(storage_root)
        self._seen_section_codes: set[str] = set()
        self._subjects: dict[str, Subject] = {}
        self._courses: dict[str, Course] = {}
        self._sections: dict[str, Section] = {}
        self._external_teachers: dict[str, Teacher] = {}
        self._alias_teachers: dict[str, list[Teacher]] = {}

    def import_path(
        self,
        path: Path,
        *,
        original_filename: str | None = None,
        content_type: str | None = None,
        term_code: str | None = None,
        sheet_name: str | None = None,
        column_mapping: dict[str, str] | None = None,
    ) -> ImportBatch:
        self._seen_section_codes.clear()
        filename = original_filename or path.name
        preserved = self.storage.preserve(path)
        parser_config: dict[str, Any] = {
            "requested_sheet": sheet_name,
            "column_mapping": column_mapping or {},
        }

        try:
            import_file = self._get_or_create_import_file(
                preserved, filename=filename, content_type=content_type
            )
            batch = ImportBatch(
                import_file=import_file,
                status=ImportStatus.PROCESSING,
                parser_config=parser_config,
                started_at=datetime.now(UTC),
            )
            self.session.add(batch)
            self.session.flush()

            table = read_offer_table(path, sheet_name)
            resolved_term = (
                normalize_term_code(term_code)
                if term_code
                else infer_term_code(filename, table.source_sheet)
            )
            term = self._get_or_create_term(resolved_term)
            batch.term = term
            batch.source_sheet = table.source_sheet
            batch.comparison_batch_id = self.session.scalar(
                select(ImportBatch.id)
                .where(
                    ImportBatch.term_id == term.id,
                    ImportBatch.id != batch.id,
                    ImportBatch.status.in_(COMPLETED_STATUSES),
                )
                .order_by(ImportBatch.finished_at.desc())
                .limit(1)
            )

            mapping = resolve_column_mapping(list(table.dataframe.columns), column_mapping)
            batch.parser_config = {
                **parser_config,
                "resolved_columns": mapping.columns,
            }
            records = table.dataframe.to_dict(orient="records")
            batch.total_rows = len(records)

            for row_index, raw_row in enumerate(records, start=2):
                row = {str(key): self._json_value(value) for key, value in raw_row.items()}
                try:
                    changed, added = self._import_row(batch, term, mapping, row, row_index)
                except RowImportError as exc:
                    batch.invalid_rows += 1
                    self._add_issue(
                        batch,
                        level=ImportIssueLevel.ERROR,
                        code=exc.code,
                        message=str(exc),
                        row_number=row_index,
                        field=exc.field,
                        raw_data=row,
                    )
                    continue
                except ValueError as exc:
                    batch.invalid_rows += 1
                    self._add_issue(
                        batch,
                        level=ImportIssueLevel.ERROR,
                        code="row.invalid_value",
                        message=str(exc),
                        row_number=row_index,
                        raw_data=row,
                    )
                    continue
                batch.imported_rows += 1
                batch.added_sections += int(added)
                batch.changed_sections += int(changed)

            deactivated = cast(
                CursorResult[Any],
                self.session.execute(
                    update(Section)
                    .where(
                        Section.term_id == term.id,
                        Section.last_seen_batch_id != batch.id,
                        Section.is_active.is_(True),
                    )
                    .values(is_active=False)
                ),
            )
            batch.removed_sections = deactivated.rowcount or 0
            batch.status = (
                ImportStatus.COMPLETED_WITH_ISSUES
                if batch.invalid_rows or batch.warning_count
                else ImportStatus.COMPLETED
            )
            batch.finished_at = datetime.now(UTC)
            self.session.commit()
            self.session.refresh(batch)
            logger.info(
                "offer import completed",
                extra={"batch_id": str(batch.id), "term": resolved_term},
            )
            return batch
        except Exception as exc:
            logger.exception("offer import failed", extra={"filename": filename})
            self.session.rollback()
            return self._record_failed_batch(
                preserved=preserved,
                filename=filename,
                content_type=content_type,
                parser_config=parser_config,
                term_code=term_code,
                error=exc,
            )

    def _record_failed_batch(
        self,
        *,
        preserved: PreservedFile,
        filename: str,
        content_type: str | None,
        parser_config: dict[str, Any],
        term_code: str | None,
        error: Exception,
    ) -> ImportBatch:
        import_file = self._get_or_create_import_file(
            preserved, filename=filename, content_type=content_type
        )
        term: Term | None = None
        try:
            inferred = normalize_term_code(term_code) if term_code else infer_term_code(filename)
            term = self._get_or_create_term(inferred)
        except ValueError:
            pass
        batch = ImportBatch(
            import_file=import_file,
            term=term,
            status=ImportStatus.FAILED,
            parser_config=parser_config,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            invalid_rows=1,
        )
        self.session.add(batch)
        self._add_issue(
            batch,
            level=ImportIssueLevel.ERROR,
            code="import.failed",
            message=str(error),
        )
        self.session.commit()
        self.session.refresh(batch)
        return batch

    def _import_row(
        self,
        batch: ImportBatch,
        term: Term,
        mapping: ResolvedColumnMapping,
        row: dict[str, Any],
        row_number: int,
    ) -> tuple[bool, bool]:
        section_code = normalize_code(mapping.get(row, "section_code"))
        subject_code = normalize_code(mapping.get(row, "subject_code"))
        subject_name = clean_text(mapping.get(row, "subject_name"))
        if section_code is None:
            raise RowImportError("section.missing_code", "codigo da turma ausente", "section_code")
        if section_code in self._seen_section_codes:
            raise RowImportError(
                "section.duplicate_code",
                f"codigo da turma repetido no arquivo: {section_code}",
                "section_code",
            )
        self._seen_section_codes.add(section_code)
        if subject_code is None:
            raise RowImportError(
                "subject.missing_code", "codigo da disciplina ausente", "subject_code"
            )
        if subject_name is None:
            raise RowImportError(
                "subject.missing_name", "nome da disciplina ausente", "subject_name"
            )

        campus = clean_text(mapping.get(row, "campus"))
        shift = clean_text(mapping.get(row, "shift"))
        total_seats = parse_optional_int(mapping.get(row, "total_seats"))
        reserved_seats = parse_optional_int(mapping.get(row, "reserved_seats"))
        workload_code = clean_text(mapping.get(row, "workload"))
        workload = self._parse_workload(workload_code)

        meetings: list[ParsedMeeting] = []
        meetings.extend(
            parse_schedule(
                mapping.get(row, "theory_schedule"),
                campus=campus,
                meeting_type=MeetingType.THEORY,
            )
        )
        meetings.extend(
            parse_schedule(
                mapping.get(row, "practice_schedule"),
                campus=campus,
                meeting_type=MeetingType.PRACTICE,
            )
        )
        if not meetings:
            raise RowImportError(
                "section.missing_meetings",
                "turma sem horario reconhecido",
                "theory_schedule",
            )

        teacher_entries = self._resolve_row_teachers(batch, mapping, row, row_number)
        if not teacher_entries:
            self._add_issue(
                batch,
                level=ImportIssueLevel.WARNING,
                code="section.no_teacher",
                message="turma importada sem docente definido",
                row_number=row_number,
                field="teacher_theory_name_1",
            )

        subject = self._get_or_create_subject(subject_code, subject_name)
        course_name = clean_text(mapping.get(row, "course_name"))
        course = self._get_or_create_course(course_name) if course_name else None
        snapshot = self._build_snapshot(
            mapping=mapping,
            row=row,
            section_code=section_code,
            subject=subject,
            campus=campus,
            shift=shift,
            total_seats=total_seats,
            reserved_seats=reserved_seats,
            workload_code=workload_code,
            meetings=meetings,
            teacher_entries=teacher_entries,
            course=course,
        )

        section = self._get_section(term, section_code)
        is_new = section is None
        if section is None:
            section = Section(
                term=term,
                subject=subject,
                first_seen_batch_id=batch.id,
                last_seen_batch_id=batch.id,
                code=section_code,
            )
            self.session.add(section)
            self._sections[section_code] = section
        previous = (
            None
            if is_new
            else self.session.scalar(
                select(SectionRevision)
                .where(SectionRevision.section_id == section.id)
                .order_by(SectionRevision.created_at.desc())
                .limit(1)
            )
        )
        changed_fields = (
            []
            if previous is None
            else sorted(
                key
                for key in set(previous.snapshot) | set(snapshot)
                if previous.snapshot.get(key) != snapshot.get(key)
            )
        )

        if not is_new:
            section.teachers.clear()
            section.meetings.clear()
            section.course_links.clear()
            self.session.flush()

        section.subject = subject
        section.last_seen_batch_id = batch.id
        section.class_group = clean_text(mapping.get(row, "class_group"))
        section.display_name = clean_text(mapping.get(row, "section_display_name"))
        section.campus = campus
        section.shift = shift
        section.total_seats = total_seats
        section.reserved_seats = reserved_seats
        section.workload_code = workload_code
        section.theory_hours = workload[0]
        section.practice_hours = workload[1]
        section.extension_hours = workload[2]
        section.individual_hours = workload[3]
        section.is_active = True
        section.teachers = [
            SectionTeacher(teacher=teacher, role=role, position=position)
            for role, position, teacher, _external_id in teacher_entries
        ]
        section.meetings = [
            SectionMeeting(
                weekday=meeting.weekday,
                start_time=meeting.start_time,
                end_time=meeting.end_time,
                campus=meeting.campus,
                classroom=meeting.classroom,
                frequency=meeting.frequency,
                meeting_type=meeting.meeting_type,
            )
            for meeting in meetings
        ]
        section.course_links = (
            [SectionCourseOffering(course=course, reserved_seats=reserved_seats)] if course else []
        )
        section.revisions.append(
            SectionRevision(
                import_batch_id=batch.id,
                fingerprint=self._fingerprint(snapshot),
                snapshot=snapshot,
                changed_fields=changed_fields,
            )
        )
        self.session.flush()
        return bool(changed_fields), is_new

    def _resolve_row_teachers(
        self,
        batch: ImportBatch,
        mapping: ResolvedColumnMapping,
        row: dict[str, Any],
        row_number: int,
    ) -> list[tuple[TeacherRole, int, Teacher, str | None]]:
        entries: list[tuple[TeacherRole, int, Teacher, str | None]] = []
        for role in (TeacherRole.THEORY, TeacherRole.PRACTICE):
            for position in range(1, 4):
                name = clean_text(mapping.get(row, f"teacher_{role.value}_name_{position}"))
                external_id = clean_text(mapping.get(row, f"teacher_{role.value}_id_{position}"))
                if external_id and external_id.endswith(".0"):
                    external_id = external_id[:-2]
                if name is None:
                    continue
                if normalize_text(name) in PLACEHOLDER_TEACHERS:
                    self._add_issue(
                        batch,
                        level=ImportIssueLevel.WARNING,
                        code="teacher.placeholder",
                        message=f"docente ainda nao definido: {name}",
                        row_number=row_number,
                        field=f"teacher_{role.value}_name_{position}",
                    )
                    continue
                teacher = self._resolve_teacher(
                    batch,
                    name=name,
                    external_id=external_id,
                    row_number=row_number,
                )
                if teacher is not None:
                    entries.append((role, position, teacher, external_id))
        return entries

    def _resolve_teacher(
        self,
        batch: ImportBatch,
        *,
        name: str,
        external_id: str | None,
        row_number: int,
    ) -> Teacher | None:
        normalized = normalize_text(name)
        if external_id:
            cached = self._external_teachers.get(external_id)
            if cached is not None:
                self._ensure_alias(cached, name, normalized)
                return cached
            identifier = self.session.scalar(
                select(ExternalTeacherIdentifier).where(
                    ExternalTeacherIdentifier.provider == "ufabc_siape",
                    ExternalTeacherIdentifier.external_id == external_id,
                )
            )
            if identifier is not None:
                teacher = identifier.teacher
            else:
                matches = self._matched_alias_teachers(normalized)
                teacher = (
                    matches[0]
                    if len(matches) == 1
                    else Teacher(
                        canonical_name=name,
                        normalized_name=normalized,
                    )
                )
                if len(matches) != 1:
                    self.session.add(teacher)
                teacher.external_identifiers.append(
                    ExternalTeacherIdentifier(provider="ufabc_siape", external_id=external_id)
                )
            self._ensure_alias(teacher, name, normalized)
            self._external_teachers[external_id] = teacher
            return teacher

        matches = self._matched_alias_teachers(normalized)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            pending = self.session.scalar(
                select(TeacherAlias).where(
                    TeacherAlias.teacher_id.is_(None),
                    TeacherAlias.normalized_name == normalized,
                    TeacherAlias.status == TeacherAliasStatus.PENDING_REVIEW,
                )
            )
            if pending is None:
                self.session.add(
                    TeacherAlias(
                        name=name,
                        normalized_name=normalized,
                        status=TeacherAliasStatus.PENDING_REVIEW,
                    )
                )
            self._add_issue(
                batch,
                level=ImportIssueLevel.WARNING,
                code="teacher.ambiguous_alias",
                message=f"nome de docente ambiguo, pendente de revisao: {name}",
                row_number=row_number,
            )
            return None

        teacher = Teacher(canonical_name=name, normalized_name=normalized)
        self.session.add(teacher)
        self._ensure_alias(teacher, name, normalized)
        self._alias_teachers[normalized] = [teacher]
        return teacher

    def _matched_alias_teachers(self, normalized: str) -> list[Teacher]:
        if normalized not in self._alias_teachers:
            aliases = self.session.scalars(
                select(TeacherAlias).where(
                    TeacherAlias.normalized_name == normalized,
                    TeacherAlias.status == TeacherAliasStatus.MATCHED,
                    TeacherAlias.teacher_id.is_not(None),
                )
            ).all()
            unique = {
                alias.teacher.id: alias.teacher for alias in aliases if alias.teacher is not None
            }
            self._alias_teachers[normalized] = list(unique.values())
        return self._alias_teachers[normalized]

    def _ensure_alias(self, teacher: Teacher, name: str, normalized: str) -> None:
        if any(alias.normalized_name == normalized for alias in teacher.aliases):
            return
        teacher.aliases.append(
            TeacherAlias(
                name=name,
                normalized_name=normalized,
                status=TeacherAliasStatus.MATCHED,
            )
        )
        matches = self._alias_teachers.setdefault(normalized, [])
        if teacher not in matches:
            matches.append(teacher)

    def _get_or_create_subject(self, code: str, name: str) -> Subject:
        subject = self._subjects.get(code)
        if subject is None:
            subject = self.session.scalar(select(Subject).where(Subject.code == code))
        if subject is None:
            subject = Subject(code=code, name=name, normalized_name=normalize_text(name))
            self.session.add(subject)
        else:
            subject.name = name
            subject.normalized_name = normalize_text(name)
        self._subjects[code] = subject
        return subject

    def _get_or_create_course(self, name: str) -> Course:
        normalized = normalize_text(name)
        course = self._courses.get(normalized)
        if course is None:
            course = self.session.scalar(
                select(Course).where(Course.normalized_name == normalized).limit(1)
            )
        if course is None:
            course = Course(
                code=generated_course_code(name),
                name=name,
                normalized_name=normalized,
                source="offer_import",
            )
            self.session.add(course)
        self._courses[normalized] = course
        return course

    def _get_section(self, term: Term, code: str) -> Section | None:
        if code not in self._sections:
            section = self.session.scalar(
                select(Section).where(Section.term_id == term.id, Section.code == code)
            )
            if section is not None:
                self._sections[code] = section
        return self._sections.get(code)

    def _get_or_create_term(self, code: str) -> Term:
        term = self.session.scalar(select(Term).where(Term.code == code))
        if term is None:
            year, term_number = code.split(":")
            term = Term(code=code, year=int(year), term_number=int(term_number))
            self.session.add(term)
            self.session.flush()
        return term

    def _get_or_create_import_file(
        self,
        preserved: PreservedFile,
        *,
        filename: str,
        content_type: str | None,
    ) -> ImportFile:
        import_file = self.session.scalar(
            select(ImportFile).where(
                ImportFile.sha256 == preserved.sha256,
                ImportFile.original_filename == filename,
            )
        )
        if import_file is None:
            import_file = ImportFile(
                original_filename=filename,
                stored_path=str(preserved.path),
                sha256=preserved.sha256,
                size_bytes=preserved.size_bytes,
                content_type=content_type,
            )
            self.session.add(import_file)
            self.session.flush()
        return import_file

    @staticmethod
    def _parse_workload(value: str | None) -> tuple[int | None, int | None, int | None, int | None]:
        if value is None:
            return None, None, None, None
        parts = value.split("-")
        if len(parts) not in (3, 4):
            raise ValueError(f"TPI/TPEI invalido: {value}")
        try:
            numbers = [int(part) for part in parts]
        except ValueError as exc:
            raise ValueError(f"TPI/TPEI invalido: {value}") from exc
        if len(numbers) == 3:
            theory, practice, individual = numbers
            return theory, practice, None, individual
        theory, practice, extension, individual = numbers
        return theory, practice, extension, individual

    @staticmethod
    def _build_snapshot(
        *,
        mapping: ResolvedColumnMapping,
        row: dict[str, Any],
        section_code: str,
        subject: Subject,
        campus: str | None,
        shift: str | None,
        total_seats: int | None,
        reserved_seats: int | None,
        workload_code: str | None,
        meetings: list[ParsedMeeting],
        teacher_entries: list[tuple[TeacherRole, int, Teacher, str | None]],
        course: Course | None,
    ) -> dict[str, Any]:
        meeting_snapshots = sorted(
            (meeting.as_snapshot() for meeting in meetings),
            key=lambda value: (
                str(value["meeting_type"]),
                int(value["weekday"] or 0),
                str(value["start_time"]),
            ),
        )
        teachers = sorted(
            (
                {
                    "role": role.value,
                    "position": position,
                    "external_id": external_id,
                    "name": teacher.canonical_name,
                    "normalized_name": teacher.normalized_name,
                }
                for role, position, teacher, external_id in teacher_entries
            ),
            key=lambda value: (str(value["role"]), int(value["position"] or 0)),
        )
        return {
            "section_code": section_code,
            "subject_code": subject.code,
            "subject_name": subject.name,
            "class_group": clean_text(mapping.get(row, "class_group")),
            "display_name": clean_text(mapping.get(row, "section_display_name")),
            "campus": campus,
            "shift": shift,
            "total_seats": total_seats,
            "reserved_seats": reserved_seats,
            "workload_code": workload_code,
            "course": course.name if course else None,
            "teachers": teachers,
            "meetings": meeting_snapshots,
        }

    @staticmethod
    def _fingerprint(snapshot: dict[str, Any]) -> str:
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _json_value(value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, float) and value != value:
            return None
        return value

    @staticmethod
    def _add_issue(
        batch: ImportBatch,
        *,
        level: ImportIssueLevel,
        code: str,
        message: str,
        row_number: int | None = None,
        field: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        batch.issues.append(
            ImportIssue(
                level=level,
                code=code,
                message=message,
                row_number=row_number,
                field=field,
                raw_data=raw_data,
            )
        )
        if level == ImportIssueLevel.WARNING:
            batch.warning_count += 1
