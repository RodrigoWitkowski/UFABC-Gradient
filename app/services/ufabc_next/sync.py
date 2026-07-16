from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import ExternalSyncStatus, TeacherAliasStatus
from app.models.imports import Term
from app.models.offerings import (
    ExternalTeacherIdentifier,
    Section,
    SectionTeacher,
    Subject,
    Teacher,
    TeacherAlias,
)
from app.models.ufabc_next import (
    ExternalSubjectIdentifier,
    SubjectReviewSnapshot,
    TeacherReviewSnapshot,
    UfabcNextComponentSnapshot,
    UfabcNextSyncRun,
)
from app.schemas.ufabc_next import UfabcNextSyncRequest
from app.services.normalization.text import normalize_code, normalize_text
from app.services.ufabc_next.cache import utc_now_naive
from app.services.ufabc_next.client import UfabcNextClient, UfabcNextError

PROVIDER = "ufabc_next"
REVIEW_PRIVATE_KEYS = {
    "__v",
    "alunos_matriculados",
    "email",
    "externalKey",
    "login",
    "ra",
    "siape",
}
COMPONENT_FIELDS = {
    "campus",
    "codigo",
    "disciplina_id",
    "enrolled_count",
    "ideal_quad",
    "pratica",
    "praticaId",
    "requisicoes",
    "season",
    "subject",
    "subjectId",
    "teoria",
    "teoriaId",
    "turma",
    "turno",
    "uf_cod_turma",
    "vagas",
}


class UfabcNextSyncError(RuntimeError):
    def __init__(self, message: str, *, run_id: uuid.UUID) -> None:
        super().__init__(message)
        self.run_id = run_id


class UfabcNextSyncService:
    def __init__(self, session: Session, client: UfabcNextClient) -> None:
        self.session = session
        self.client = client

    def sync(self, options: UfabcNextSyncRequest) -> UfabcNextSyncRun:
        term = self.session.scalar(select(Term).where(Term.code == options.season))
        if term is None:
            raise ValueError(
                "quadrimestre nao encontrado; importe a planilha de ofertas antes do Next"
            )
        run = UfabcNextSyncRun(
            season=options.season,
            status=ExternalSyncStatus.RUNNING,
            include_teacher_reviews=options.include_teacher_reviews,
            include_subject_reviews=options.include_subject_reviews,
            force_refresh=options.force_refresh,
            started_at=utc_now_naive(),
            warnings=[],
            request_log=[],
        )
        self.session.add(run)
        self.session.commit()

        try:
            components = self.client.get_components(
                options.season,
                force_refresh=options.force_refresh,
            )
            teacher_ids, subject_ids = self._persist_components(run, term, components)
            if options.include_teacher_reviews:
                run.teacher_reviews_synced = self._sync_teacher_reviews(
                    run,
                    teacher_ids,
                    limit=options.review_limit,
                    force_refresh=options.force_refresh,
                )
            if options.include_subject_reviews:
                run.subject_reviews_synced = self._sync_subject_reviews(
                    run,
                    subject_ids,
                    limit=options.review_limit,
                    force_refresh=options.force_refresh,
                )
            run.remote_requests = self.client.remote_requests
            run.cache_hits = self.client.cache_hits
            run.request_log = self.client.request_log
            run.status = (
                ExternalSyncStatus.COMPLETED_WITH_WARNINGS
                if run.warnings
                else ExternalSyncStatus.COMPLETED
            )
            run.finished_at = utc_now_naive()
            self.session.commit()
            return run
        except Exception as exc:
            self.session.rollback()
            failed_run = self.session.get(UfabcNextSyncRun, run.id)
            if failed_run is not None:
                failed_run.status = ExternalSyncStatus.FAILED
                failed_run.finished_at = utc_now_naive()
                failed_run.remote_requests = self.client.remote_requests
                failed_run.cache_hits = self.client.cache_hits
                failed_run.request_log = self.client.request_log
                failed_run.error_message = str(exc)[:2000]
                self.session.commit()
            raise UfabcNextSyncError(str(exc), run_id=run.id) from exc

    def _persist_components(
        self,
        run: UfabcNextSyncRun,
        term: Term,
        components: list[dict[str, Any]],
    ) -> tuple[set[str], set[str]]:
        sections = (
            self.session.scalars(
                select(Section)
                .where(Section.term_id == term.id)
                .options(
                    selectinload(Section.subject),
                    selectinload(Section.teachers).selectinload(SectionTeacher.teacher),
                )
            )
            .unique()
            .all()
        )
        sections_by_code = {section.code: section for section in sections}
        subjects = self.session.scalars(select(Subject)).all()
        subjects_by_code = {subject.code: subject for subject in subjects}
        teachers_by_name = self._teachers_by_normalized_name()
        external_teachers = {
            item.external_id: item
            for item in self.session.scalars(
                select(ExternalTeacherIdentifier)
                .where(ExternalTeacherIdentifier.provider == PROVIDER)
                .options(selectinload(ExternalTeacherIdentifier.teacher))
            ).all()
        }
        external_subjects = {
            (item.external_id, item.subject_id): item
            for item in self.session.scalars(
                select(ExternalSubjectIdentifier).where(
                    ExternalSubjectIdentifier.provider == PROVIDER
                )
            ).all()
        }
        teacher_ids: set[str] = set()
        subject_ids: set[str] = set()
        matched = 0

        for item in components:
            section_code = self._required_string(item, "uf_cod_turma")
            section = sections_by_code.get(section_code)
            subject_code = normalize_code(self._optional_string(item.get("codigo")))
            subject = section.subject if section is not None else None
            if subject is None and subject_code is not None:
                subject = subjects_by_code.get(subject_code)
            external_subject_id = self._optional_string(item.get("subjectId"))
            if section is not None:
                matched += 1
            if external_subject_id:
                subject_ids.add(external_subject_id)
                if subject is not None:
                    self._link_subject_identifier(
                        subject,
                        external_subject_id,
                        external_subjects,
                    )

            for name_field, id_field in (("teoria", "teoriaId"), ("pratica", "praticaId")):
                external_teacher_id = self._optional_string(item.get(id_field))
                teacher_name = self._optional_string(item.get(name_field))
                if external_teacher_id is None:
                    continue
                teacher_ids.add(external_teacher_id)
                self._link_teacher_identifier(
                    external_teacher_id,
                    teacher_name,
                    section,
                    external_teachers,
                    teachers_by_name,
                    run.warnings,
                )

            enrolled_count = self._optional_int(item.get("enrolled_count")) or 0
            sanitized = {key: value for key, value in item.items() if key in COMPONENT_FIELDS}
            sanitized["enrolled_count"] = enrolled_count
            self.session.add(
                UfabcNextComponentSnapshot(
                    sync_run_id=run.id,
                    term_id=term.id,
                    section_id=section.id if section else None,
                    subject_id=subject.id if subject else None,
                    external_component_id=self._optional_string(item.get("disciplina_id")),
                    external_section_code=section_code,
                    external_subject_id=external_subject_id,
                    seats=self._optional_int(item.get("vagas")),
                    requests=self._optional_int(item.get("requisicoes")),
                    enrolled_count=enrolled_count,
                    ideal_term=self._optional_bool(item.get("ideal_quad")),
                    payload=sanitized,
                )
            )

        run.components_received = len(components)
        run.components_matched = matched
        run.components_unmatched = len(components) - matched
        if run.components_unmatched:
            run.warnings.append(
                f"{run.components_unmatched} componentes do Next nao correspondem "
                "a uma turma da planilha"
            )
        self.session.flush()
        return teacher_ids, subject_ids

    def _sync_teacher_reviews(
        self,
        run: UfabcNextSyncRun,
        external_ids: set[str],
        *,
        limit: int,
        force_refresh: bool,
    ) -> int:
        identifiers = {
            item.external_id: item.teacher_id
            for item in self.session.scalars(
                select(ExternalTeacherIdentifier).where(
                    ExternalTeacherIdentifier.provider == PROVIDER,
                    ExternalTeacherIdentifier.external_id.in_(external_ids),
                )
            ).all()
        }
        selected = sorted(external_ids)[:limit]
        if len(external_ids) > limit:
            run.warnings.append(
                f"reviews de professores limitados a {limit} de {len(external_ids)} identificadores"
            )
        synced = 0
        for external_id in selected:
            try:
                payload = self.client.get_teacher_reviews(
                    external_id,
                    force_refresh=force_refresh,
                )
            except UfabcNextError as exc:
                run.warnings.append(f"review do professor {external_id} falhou: {exc}")
                continue
            general, distribution = self._review_general(payload)
            specific = payload.get("specific")
            self.session.add(
                TeacherReviewSnapshot(
                    sync_run_id=run.id,
                    teacher_id=identifiers.get(external_id),
                    external_teacher_id=external_id,
                    sample_size=self._optional_int(general.get("count")) or 0,
                    metrics=general,
                    distribution=distribution,
                    specific_statistics=self._sanitize_review_list(specific),
                    fetched_at=utc_now_naive(),
                )
            )
            synced += 1
        self.session.flush()
        return synced

    def _sync_subject_reviews(
        self,
        run: UfabcNextSyncRun,
        external_ids: set[str],
        *,
        limit: int,
        force_refresh: bool,
    ) -> int:
        identifier_subjects: dict[str, set[uuid.UUID]] = defaultdict(set)
        for item in self.session.scalars(
            select(ExternalSubjectIdentifier).where(
                ExternalSubjectIdentifier.provider == PROVIDER,
                ExternalSubjectIdentifier.external_id.in_(external_ids),
            )
        ).all():
            identifier_subjects[item.external_id].add(item.subject_id)
        identifiers = {
            external_id: next(iter(subject_ids)) if len(subject_ids) == 1 else None
            for external_id, subject_ids in identifier_subjects.items()
        }
        selected = sorted(external_ids)[:limit]
        if len(external_ids) > limit:
            run.warnings.append(
                f"reviews de disciplinas limitados a {limit} de {len(external_ids)} identificadores"
            )
        synced = 0
        for external_id in selected:
            try:
                payload = self.client.get_subject_reviews(
                    external_id,
                    force_refresh=force_refresh,
                )
            except UfabcNextError as exc:
                run.warnings.append(f"review da disciplina {external_id} falhou: {exc}")
                continue
            general, distribution = self._review_general(payload)
            specific = payload.get("specific")
            self.session.add(
                SubjectReviewSnapshot(
                    sync_run_id=run.id,
                    subject_id=identifiers.get(external_id),
                    external_subject_id=external_id,
                    sample_size=self._optional_int(general.get("count")) or 0,
                    metrics=general,
                    distribution=distribution,
                    teacher_statistics=self._sanitize_review_list(specific),
                    fetched_at=utc_now_naive(),
                )
            )
            synced += 1
        self.session.flush()
        return synced

    def _teachers_by_normalized_name(self) -> dict[str, list[Teacher]]:
        teachers = (
            self.session.scalars(select(Teacher).options(selectinload(Teacher.aliases)))
            .unique()
            .all()
        )
        result: dict[str, dict[uuid.UUID, Teacher]] = defaultdict(dict)
        for teacher in teachers:
            result[teacher.normalized_name][teacher.id] = teacher
            for alias in teacher.aliases:
                if alias.status == TeacherAliasStatus.MATCHED:
                    result[alias.normalized_name][teacher.id] = teacher
        return {name: list(matches.values()) for name, matches in result.items()}

    def _link_teacher_identifier(
        self,
        external_id: str,
        name: str | None,
        section: Section | None,
        identifiers: dict[str, ExternalTeacherIdentifier],
        teachers_by_name: dict[str, list[Teacher]],
        warnings: list[str],
    ) -> Teacher | None:
        existing = identifiers.get(external_id)
        if existing is not None:
            return existing.teacher
        if name is None:
            warnings.append(f"professor {external_id} retornado sem nome")
            return None
        normalized = normalize_text(name)
        section_matches = []
        if section is not None:
            section_matches = [
                item.teacher
                for item in section.teachers
                if item.teacher.normalized_name == normalized
            ]
        candidates = self._unique_teachers(section_matches or teachers_by_name.get(normalized, []))
        if len(candidates) > 1:
            warnings.append(f"nome de professor ambiguo no Next: {name}")
            return None
        if candidates:
            teacher = candidates[0]
        else:
            teacher = Teacher(canonical_name=name, normalized_name=normalized)
            teacher.aliases.append(
                TeacherAlias(
                    name=name,
                    normalized_name=normalized,
                    status=TeacherAliasStatus.MATCHED,
                    source=PROVIDER,
                )
            )
            self.session.add(teacher)
            self.session.flush()
            teachers_by_name.setdefault(normalized, []).append(teacher)
        identifier = ExternalTeacherIdentifier(
            teacher=teacher,
            provider=PROVIDER,
            external_id=external_id,
        )
        self.session.add(identifier)
        identifiers[external_id] = identifier
        return teacher

    def _link_subject_identifier(
        self,
        subject: Subject,
        external_id: str,
        identifiers: dict[tuple[str, uuid.UUID], ExternalSubjectIdentifier],
    ) -> None:
        key = (external_id, subject.id)
        existing = identifiers.get(key)
        if existing is not None:
            return
        identifier = ExternalSubjectIdentifier(
            subject_id=subject.id,
            provider=PROVIDER,
            external_id=external_id,
        )
        self.session.add(identifier)
        identifiers[key] = identifier

    @classmethod
    def _review_general(
        cls,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        raw_general = payload.get("general")
        if not isinstance(raw_general, dict):
            return {}, []
        raw_distribution = raw_general.get("distribution")
        metrics = {
            key: cls._sanitize_review_value(value)
            for key, value in raw_general.items()
            if key != "distribution" and key not in REVIEW_PRIVATE_KEYS
        }
        distribution = cls._sanitize_review_list(raw_distribution)
        return metrics, distribution

    @classmethod
    def _sanitize_review_list(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [
            sanitized
            for item in value
            if isinstance(item, dict)
            if isinstance((sanitized := cls._sanitize_review_value(item)), dict)
        ]

    @classmethod
    def _sanitize_review_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._sanitize_review_value(item)
                for key, item in value.items()
                if key not in REVIEW_PRIVATE_KEYS
            }
        if isinstance(value, list):
            return [cls._sanitize_review_value(item) for item in value]
        return value

    @staticmethod
    def _unique_teachers(teachers: list[Teacher]) -> list[Teacher]:
        return list({teacher.id: teacher for teacher in teachers}.values())

    @staticmethod
    def _required_string(payload: dict[str, Any], key: str) -> str:
        value = UfabcNextSyncService._optional_string(payload.get(key))
        if value is None:
            raise ValueError(f"componente do Next sem campo obrigatorio: {key}")
        return value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_bool(value: Any) -> bool | None:
        return value if isinstance(value, bool) else None
