from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.serializers import serialize_section
from app.models.curriculum import CourseCurriculumSubject
from app.models.enums import (
    CourseStrategy,
    CurriculumCategory,
    CurriculumCategorySource,
)
from app.models.imports import Term
from app.models.offerings import Section, SectionCourseOffering, SectionTeacher
from app.models.rankings import Ranking, RankingItem
from app.models.statistics import TeacherStatistics, TeacherSubjectStatistics
from app.models.students import StudentCourse, StudentProfile
from app.models.ufabc_next import UfabcNextComponentSnapshot, UfabcNextSyncRun
from app.schemas.rankings import (
    EnrollmentPriorityRead,
    RankingConfig,
    RankingCurriculumClassificationRead,
    RankingHardConstraints,
    RankingItemRead,
    RankingRead,
    RankingRerankRequest,
    RankingSoftPreferences,
    RankingTeacherStatisticsRead,
    SeatProbabilityRead,
    SectionRankingRequest,
)
from app.schemas.statistics import TeacherStatisticsEvaluationRequest
from app.services.enrollment import EnrollmentPriorityEvaluator
from app.services.normalization.text import normalize_text
from app.services.statistics import TeacherStatisticsEvaluator
from app.services.students import StudentNotFoundError, StudentService
from app.services.ufabc_next.cache import utc_now_naive


class RankingNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class _RankedCandidate:
    section: Section
    total_score: float
    score_breakdown: dict[str, float]
    classifications: list[RankingCurriculumClassificationRead]
    teacher_statistics: list[RankingTeacherStatisticsRead]
    seat_probability: SeatProbabilityRead
    explanations: list[str]
    warnings: list[str]


class RankingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_ranking(
        self,
        payload: SectionRankingRequest,
        *,
        source_ranking_id: uuid.UUID | None = None,
    ) -> Ranking:
        term = self.session.scalar(select(Term).where(Term.code == payload.term))
        if term is None:
            raise ValueError("quadrimestre nao encontrado")
        try:
            student = StudentService(self.session).get_student(payload.student_id)
        except StudentNotFoundError:
            raise
        if not student.courses:
            raise ValueError("o perfil do aluno precisa ter pelo menos um curso")
        config, preference_warnings = self._effective_config(student, payload.config)

        sections = list(
            self.session.scalars(
                select(Section)
                .where(Section.term_id == term.id, Section.is_active.is_(True))
                .options(
                    selectinload(Section.subject),
                    selectinload(Section.teachers).selectinload(SectionTeacher.teacher),
                    selectinload(Section.meetings),
                    selectinload(Section.course_links).selectinload(
                        SectionCourseOffering.course
                    ),
                )
                .order_by(Section.code)
            ).all()
        )
        entry_map = self._curriculum_entries(sections, student)
        sections, filter_warnings = self._apply_hard_constraints(
            sections, student, config, entry_map
        )
        component_map = self._component_snapshots(term, sections)
        general_statistics, specific_statistics = self._teacher_statistics(sections)

        candidates = [
            self._rank_section(
                section,
                term,
                student,
                config,
                entry_map,
                component_map.get(section.id),
                general_statistics,
                specific_statistics,
            )
            for section in sections
        ]
        candidates.sort(key=lambda item: (-item.total_score, item.section.code))
        selected = candidates[: payload.result_limit]
        warnings = [
            "A porcentagem de vagas representa vagas/solicitacoes da turma, nao a chance "
            "pessoal de matricula.",
            "A prioridade individual segue curso, turno, CP e CA conforme a regra "
            "versionada; CR, IK e campus nao alteram essa ordem.",
            *preference_warnings,
            *filter_warnings,
        ]
        if len(candidates) > payload.result_limit:
            warnings.append(
                f"Resposta limitada as {payload.result_limit} primeiras de "
                f"{len(candidates)} turmas candidatas."
            )

        ranking = Ranking(
            term_id=term.id,
            student_profile_id=student.id,
            source_ranking_id=source_ranking_id,
            config=config.model_dump(mode="json"),
            result_limit=payload.result_limit,
            candidate_count=len(candidates),
            item_count=len(selected),
            warnings=warnings,
            computed_at=utc_now_naive(),
        )
        self.session.add(ranking)
        self.session.flush()
        for position, candidate in enumerate(selected, start=1):
            ranking.items.append(
                RankingItem(
                    section_id=candidate.section.id,
                    position=position,
                    total_score=Decimal(str(candidate.total_score)),
                    score_breakdown=candidate.score_breakdown,
                    section_snapshot=serialize_section(candidate.section).model_dump(mode="json"),
                    curriculum_classifications=[
                        item.model_dump(mode="json") for item in candidate.classifications
                    ],
                    teacher_statistics=[
                        item.model_dump(mode="json") for item in candidate.teacher_statistics
                    ],
                    seat_probability=candidate.seat_probability.model_dump(mode="json"),
                    explanations=candidate.explanations,
                    warnings=candidate.warnings,
                )
            )
        self.session.flush()
        return ranking

    def get_ranking(self, ranking_id: uuid.UUID) -> Ranking:
        ranking = self.session.scalar(
            select(Ranking)
            .where(Ranking.id == ranking_id)
            .options(selectinload(Ranking.term), selectinload(Ranking.items))
        )
        if ranking is None:
            raise RankingNotFoundError("ranking nao encontrado")
        return ranking

    def rerank(self, ranking_id: uuid.UUID, payload: RankingRerankRequest) -> Ranking:
        source = self.get_ranking(ranking_id)
        return self.create_ranking(
            SectionRankingRequest(
                term=source.term.code,
                student_id=source.student_profile_id,
                result_limit=payload.result_limit or source.result_limit,
                config=payload.config,
            ),
            source_ranking_id=source.id,
        )

    def serialize(self, ranking: Ranking) -> RankingRead:
        return RankingRead(
            id=ranking.id,
            term=ranking.term.code,
            student_id=ranking.student_profile_id,
            source_ranking_id=ranking.source_ranking_id,
            result_limit=ranking.result_limit,
            candidate_count=ranking.candidate_count,
            item_count=ranking.item_count,
            config=RankingConfig.model_validate(ranking.config),
            warnings=ranking.warnings,
            computed_at=ranking.computed_at,
            items=[
                RankingItemRead(
                    id=item.id,
                    position=item.position,
                    section=item.section_snapshot,
                    total_score=float(item.total_score),
                    score_breakdown=item.score_breakdown,
                    curriculum_classifications=item.curriculum_classifications,
                    teacher_statistics=item.teacher_statistics,
                    seat_probability=item.seat_probability,
                    explanations=item.explanations,
                    warnings=item.warnings,
                )
                for item in ranking.items
            ],
        )

    def _effective_config(
        self, student: StudentProfile, config: RankingConfig
    ) -> tuple[RankingConfig, list[str]]:
        warnings: list[str] = []
        saved_hard: dict[str, Any] = {}
        saved_soft: dict[str, Any] = {}
        if student.preferences is not None:
            saved_hard = student.preferences.hard_constraints
            saved_soft = student.preferences.soft_preferences

        hard = config.hard_constraints
        if hard is None:
            hard = RankingHardConstraints.model_validate(saved_hard)
            unknown_hard = set(saved_hard) - {
                "allowed_shifts",
                "excluded_weekdays",
                "allowed_campuses",
                "earliest_start_time",
                "latest_end_time",
                "excluded_teacher_ids",
                "excluded_subject_ids",
                "max_subject_credits",
                "max_credits",
            }
            if unknown_hard:
                warnings.append(
                    "Restricoes salvas ainda nao suportadas: "
                    + ", ".join(sorted(unknown_hard))
                    + "."
                )

        soft = config.soft_preferences
        if soft is None:
            soft = RankingSoftPreferences.model_validate(saved_soft)
            unknown_soft = set(saved_soft) - {
                "prefer_night",
                "avoid_friday",
                "avoid_early_classes",
                "preferred_earliest_start",
                "prefer_fewer_campus_days",
                "preferred_campuses",
            }
            if unknown_soft:
                warnings.append(
                    "Preferencias salvas ainda nao suportadas: "
                    + ", ".join(sorted(unknown_soft))
                    + "."
                )
        return config.model_copy(
            update={"hard_constraints": hard, "soft_preferences": soft}
        ), warnings

    def _apply_hard_constraints(
        self,
        sections: list[Section],
        student: StudentProfile,
        config: RankingConfig,
        entry_map: dict[tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject],
    ) -> tuple[list[Section], list[str]]:
        excluded_subjects: set[uuid.UUID] = set()
        if config.exclude_completed_subjects:
            excluded_subjects.update(item.subject_id for item in student.completed_subjects)
        if config.exclude_in_progress_subjects:
            excluded_subjects.update(item.subject_id for item in student.in_progress_subjects)
        constraints = config.hard_constraints or RankingHardConstraints()
        excluded_subjects.update(constraints.excluded_subject_ids)
        excluded_teachers = set(constraints.excluded_teacher_ids)
        allowed_shifts = {normalize_text(item) for item in constraints.allowed_shifts}
        allowed_campuses = {normalize_text(item) for item in constraints.allowed_campuses}
        excluded_weekdays = set(constraints.excluded_weekdays)
        reason_counts: defaultdict[str, int] = defaultdict(int)
        accepted: list[Section] = []
        for section in sections:
            reasons: list[str] = []
            if section.subject_id in excluded_subjects:
                reasons.append("disciplina concluida, em andamento ou bloqueada")
            if excluded_teachers.intersection(item.teacher_id for item in section.teachers):
                reasons.append("docente bloqueado")
            if allowed_shifts and (
                section.shift is None or normalize_text(section.shift) not in allowed_shifts
            ):
                reasons.append("turno nao permitido")
            if allowed_campuses and (
                section.campus is None or normalize_text(section.campus) not in allowed_campuses
            ):
                reasons.append("campus nao permitido")
            if excluded_weekdays.intersection(item.weekday for item in section.meetings):
                reasons.append("dia da semana excluido")
            if constraints.earliest_start_time is not None and any(
                item.start_time < constraints.earliest_start_time for item in section.meetings
            ):
                reasons.append("inicio anterior ao horario minimo")
            if constraints.latest_end_time is not None and any(
                item.end_time > constraints.latest_end_time for item in section.meetings
            ):
                reasons.append("termino posterior ao horario maximo")
            if constraints.max_subject_credits is not None:
                credits = self._section_credits(section, student, entry_map)
                if credits is not None and credits > constraints.max_subject_credits:
                    reasons.append("creditos acima do maximo por disciplina")
            if reasons:
                for reason in set(reasons):
                    reason_counts[reason] += 1
            else:
                accepted.append(section)
        warnings = [
            f"{count} turma(s) violaram o filtro: {reason}."
            for reason, count in sorted(reason_counts.items())
        ]
        return accepted, warnings

    def _curriculum_entries(
        self, sections: list[Section], student: StudentProfile
    ) -> dict[tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject]:
        curriculum_ids = [item.curriculum_version_id for item in student.courses]
        subject_ids = list({item.subject_id for item in sections})
        if not curriculum_ids or not subject_ids:
            return {}
        entries = self.session.scalars(
            select(CourseCurriculumSubject).where(
                CourseCurriculumSubject.curriculum_version_id.in_(curriculum_ids),
                CourseCurriculumSubject.subject_id.in_(subject_ids),
            )
        ).all()
        return {(item.curriculum_version_id, item.subject_id): item for item in entries}

    def _component_snapshots(
        self, term: Term, sections: list[Section]
    ) -> dict[uuid.UUID, UfabcNextComponentSnapshot]:
        section_ids = [item.id for item in sections]
        if not section_ids:
            return {}
        snapshots = self.session.scalars(
            select(UfabcNextComponentSnapshot)
            .join(UfabcNextSyncRun)
            .where(
                UfabcNextComponentSnapshot.term_id == term.id,
                UfabcNextComponentSnapshot.section_id.in_(section_ids),
            )
            .order_by(
                UfabcNextSyncRun.created_at.desc(),
                UfabcNextComponentSnapshot.created_at.desc(),
            )
        ).all()
        latest: dict[uuid.UUID, UfabcNextComponentSnapshot] = {}
        for snapshot in snapshots:
            if snapshot.section_id is not None:
                latest.setdefault(snapshot.section_id, snapshot)
        return latest

    def _teacher_statistics(
        self, sections: list[Section]
    ) -> tuple[
        dict[uuid.UUID, TeacherStatistics],
        dict[tuple[uuid.UUID, uuid.UUID], TeacherSubjectStatistics],
    ]:
        teacher_ids = list(
            {teacher.teacher_id for section in sections for teacher in section.teachers}
        )
        subject_ids = list({section.subject_id for section in sections})
        if not teacher_ids:
            return {}, {}
        general_rows = self.session.scalars(
            select(TeacherStatistics)
            .where(TeacherStatistics.teacher_id.in_(teacher_ids))
            .order_by(
                TeacherStatistics.sample_size.desc(),
                TeacherStatistics.source_fetched_at.desc(),
            )
        ).all()
        general: dict[uuid.UUID, TeacherStatistics] = {}
        for general_row in general_rows:
            if general_row.teacher_id is not None:
                general.setdefault(general_row.teacher_id, general_row)

        specific: dict[tuple[uuid.UUID, uuid.UUID], TeacherSubjectStatistics] = {}
        if subject_ids:
            specific_rows = self.session.scalars(
                select(TeacherSubjectStatistics)
                .where(
                    TeacherSubjectStatistics.teacher_id.in_(teacher_ids),
                    TeacherSubjectStatistics.subject_id.in_(subject_ids),
                )
                .order_by(
                    TeacherSubjectStatistics.sample_size.desc(),
                    TeacherSubjectStatistics.source_fetched_at.desc(),
                )
            ).all()
            for specific_row in specific_rows:
                if specific_row.teacher_id is not None and specific_row.subject_id is not None:
                    specific.setdefault(
                        (specific_row.teacher_id, specific_row.subject_id), specific_row
                    )
        return general, specific

    def _rank_section(
        self,
        section: Section,
        term: Term,
        student: StudentProfile,
        config: RankingConfig,
        entry_map: dict[tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject],
        component: UfabcNextComponentSnapshot | None,
        general_statistics: dict[uuid.UUID, TeacherStatistics],
        specific_statistics: dict[tuple[uuid.UUID, uuid.UUID], TeacherSubjectStatistics],
    ) -> _RankedCandidate:
        classifications, curriculum_score = self._curriculum_score(
            section, term, student, config, entry_map
        )
        teacher_statistics, teacher_score, teacher_warnings = self._teacher_score(
            section, config, general_statistics, specific_statistics
        )
        priority = EnrollmentPriorityEvaluator().evaluate(
            section=section,
            term=term,
            student=student,
            curriculum_entries=entry_map,
        )
        seat_probability = self._seat_probability(section, component, config, priority)
        soft_preferences = config.soft_preferences or RankingSoftPreferences()
        schedule_score, schedule_explanations = self._schedule_score(
            section, student, soft_preferences
        )
        campus_score, campus_explanation = self._campus_score(section, student, soft_preferences)
        workload_score, workload_explanation = self._workload_score(
            section, classifications, config
        )
        score_breakdown = {
            "curriculum_relevance": curriculum_score,
            "teacher": teacher_score,
            "seat_probability": seat_probability.score,
            "schedule_preference": schedule_score,
            "workload": workload_score,
            "campus": campus_score,
        }
        weights = config.weights.model_dump()
        total_score = round(
            sum(score_breakdown[name] * weights[name] for name in score_breakdown),
            6,
        )
        explanations = [
            self._curriculum_summary(classifications, config, student),
            *schedule_explanations,
            campus_explanation,
            *([workload_explanation] if weights["workload"] > 0 else []),
        ]
        warnings = [*teacher_warnings, *seat_probability.warnings]
        return _RankedCandidate(
            section=section,
            total_score=total_score,
            score_breakdown=score_breakdown,
            classifications=classifications,
            teacher_statistics=teacher_statistics,
            seat_probability=seat_probability,
            explanations=explanations,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _curriculum_score(
        self,
        section: Section,
        term: Term,
        student: StudentProfile,
        config: RankingConfig,
        entry_map: dict[tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject],
    ) -> tuple[list[RankingCurriculumClassificationRead], float]:
        estimated_term = max(1, (term.year - student.admission_year) * 3 + term.term_number)
        classifications: list[RankingCurriculumClassificationRead] = []
        for student_course in student.courses:
            entry = entry_map.get((student_course.curriculum_version_id, section.subject_id))
            category: CurriculumCategory | None
            source: CurriculumCategorySource | None
            if entry is not None:
                category = entry.category
                source = entry.category_source
                ideal_term = entry.ideal_term
                credits = float(entry.credits) if entry.credits is not None else None
            else:
                category = student_course.curriculum_version.unlisted_subject_category
                source = CurriculumCategorySource.DERIVED_RULE if category is not None else None
                ideal_term = None
                credits = None
            relevance = self._category_relevance(category, ideal_term, estimated_term, config)
            category_name = category.value if category is not None else "unclassified"
            explanation = (
                f"{category_name} em {student_course.course.code} "
                f"({student_course.curriculum_version.version}), nota {relevance:.2f}."
            )
            classifications.append(
                RankingCurriculumClassificationRead(
                    course_id=student_course.course_id,
                    course_code=student_course.course.code,
                    curriculum_version_id=student_course.curriculum_version_id,
                    curriculum_version=student_course.curriculum_version.version,
                    category=category,
                    category_source=source,
                    ideal_term=ideal_term,
                    student_estimated_term=estimated_term,
                    credits=credits,
                    relevance_score=relevance,
                    explanation=explanation,
                )
            )
        strategy = config.course_strategy or student.course_strategy
        return classifications, self._combine_course_scores(
            classifications, student.courses, strategy
        )

    def _category_relevance(
        self,
        category: CurriculumCategory | None,
        ideal_term: int | None,
        estimated_term: int,
        config: RankingConfig,
    ) -> float:
        weights = config.curriculum_weights
        if category == CurriculumCategory.MANDATORY:
            value = (
                weights.mandatory_ideal
                if ideal_term is not None and ideal_term == estimated_term
                else weights.mandatory
            )
        elif category == CurriculumCategory.LIMITED:
            value = weights.limited
        elif category == CurriculumCategory.FREE:
            value = weights.free
        elif category == CurriculumCategory.NOT_APPLICABLE:
            value = weights.not_applicable
        else:
            value = weights.unclassified
        return round(value * 100, 6)

    def _combine_course_scores(
        self,
        classifications: list[RankingCurriculumClassificationRead],
        student_courses: list[StudentCourse],
        strategy: CourseStrategy,
    ) -> float:
        scores = {item.course_id: item.relevance_score for item in classifications}
        if strategy == CourseStrategy.PRIMARY_COURSE:
            primary = next((item for item in student_courses if item.is_primary), None)
            if primary is None:
                raise ValueError("o perfil do aluno nao possui curso principal")
            return scores[primary.course_id]
        if strategy == CourseStrategy.MAXIMIZE_ANY_COURSE_PROGRESS:
            return max(scores.values(), default=0.0)
        if strategy == CourseStrategy.MAXIMIZE_ALL_COURSES_PROGRESS:
            return round(sum(scores.values()) / len(scores), 6) if scores else 0.0

        total = 0.0
        for course in student_courses:
            if course.weight is None:
                raise ValueError("a estrategia weighted_courses exige peso em todos os cursos")
            total += scores[course.course_id] * float(course.weight)
        return round(total, 6)

    def _teacher_score(
        self,
        section: Section,
        config: RankingConfig,
        general_statistics: dict[uuid.UUID, TeacherStatistics],
        specific_statistics: dict[tuple[uuid.UUID, uuid.UUID], TeacherSubjectStatistics],
    ) -> tuple[list[RankingTeacherStatisticsRead], float, list[str]]:
        settings = config.teacher_statistics
        evaluator = TeacherStatisticsEvaluator(self.session)
        results: list[RankingTeacherStatisticsRead] = []
        warnings: list[str] = []
        for section_teacher in section.teachers:
            request = TeacherStatisticsEvaluationRequest(
                teacher_id=section_teacher.teacher_id,
                subject_id=section.subject_id,
                mode=settings.mode,
                metric=settings.metric,
                use_bayesian_adjustment=settings.use_bayesian_adjustment,
                prior_weight=settings.prior_weight,
                confidence_constant=settings.confidence_constant,
                grade_weights=settings.grade_weights,
            )
            evaluation = evaluator.evaluate_from_rows(
                request,
                general_statistics.get(section_teacher.teacher_id),
                specific_statistics.get((section_teacher.teacher_id, section.subject_id)),
            )
            score = evaluation.score if evaluation.score is not None else settings.missing_score
            if not evaluation.available:
                warnings.append(
                    f"Sem estatistica para {section_teacher.teacher.canonical_name}; "
                    f"usada nota neutra {settings.missing_score:.2f}."
                )
            warnings.extend(evaluation.warnings)
            results.append(
                RankingTeacherStatisticsRead(
                    teacher_id=section_teacher.teacher_id,
                    teacher_name=section_teacher.teacher.canonical_name,
                    role=section_teacher.role,
                    position=section_teacher.position,
                    score=score,
                    statistics_available=evaluation.available,
                    evaluation=evaluation,
                )
            )
        if not results:
            warnings.append(
                f"Turma sem docente identificado; usada nota neutra {settings.missing_score:.2f}."
            )
            return [], settings.missing_score, warnings
        return results, round(sum(item.score for item in results) / len(results), 6), warnings

    def _seat_probability(
        self,
        section: Section,
        component: UfabcNextComponentSnapshot | None,
        config: RankingConfig,
        priority: EnrollmentPriorityRead,
    ) -> SeatProbabilityRead:
        seats = (
            component.seats
            if component is not None and component.seats is not None
            else section.total_seats
        )
        requests = component.requests if component is not None else None
        enrolled = component.enrolled_count if component is not None else None
        source = "ufabc_next_snapshot" if component is not None else "official_offer"
        if seats is None or requests is None or requests <= 0:
            reason = (
                "Demanda igual a zero foi tratada como indisponivel, pois as solicitacoes "
                "podem ainda nao ter sido abertas."
                if requests == 0
                else "Vagas ou demanda indisponiveis para esta turma."
            )
            return SeatProbabilityRead(
                estimated_probability=None,
                personalized_probability=None,
                probability_basis="unavailable",
                score=config.missing_seat_probability_score,
                confidence="none",
                seats=seats,
                requests=requests,
                enrolled_count=enrolled,
                source=source,
                favorable_factors=[],
                risk_factors=[],
                warnings=[
                    reason,
                    "Probabilidade pessoal indisponivel sem distribuicao dos solicitantes.",
                ],
                priority=priority,
            )
        probability = min(max(seats / requests, 0.0), 1.0)
        favorable = []
        risks = []
        if seats <= 0:
            risks.append("A turma nao possui vagas disponiveis.")
        elif requests <= seats:
            favorable.append("A demanda observada nao supera as vagas.")
        else:
            risks.append(f"Ha {requests / seats:.2f} solicitacoes por vaga.")
        return SeatProbabilityRead(
            estimated_probability=probability,
            personalized_probability=None,
            probability_basis="aggregate_seats_over_requests",
            score=round(probability * 100, 6),
            confidence="low",
            seats=seats,
            requests=requests,
            enrolled_count=enrolled,
            source=source,
            favorable_factors=favorable,
            risk_factors=risks,
            warnings=[
                "Estimativa agregada por vagas/demanda; nao e uma probabilidade pessoal.",
                "A prioridade foi analisada, mas falta a distribuicao dos demais "
                "solicitantes para converte-la em porcentagem.",
            ],
            priority=priority,
        )

    def _schedule_score(
        self,
        section: Section,
        student: StudentProfile,
        preferences: RankingSoftPreferences,
    ) -> tuple[float, list[str]]:
        dimensions: list[tuple[float, float]] = []
        explanations: list[str] = []
        if not student.admission_shift or not section.shift:
            dimensions.append((50.0, 1.0))
            explanations.append("Turno sem comparacao completa; usada nota neutra 50.")
        elif normalize_text(student.admission_shift) == normalize_text(section.shift):
            dimensions.append((100.0, 1.0))
            explanations.append(f"Turno {section.shift} coincide com o turno do aluno.")
        else:
            dimensions.append((25.0, 1.0))
            explanations.append(f"Turno {section.shift} difere do turno {student.admission_shift}.")

        if preferences.prefer_night > 0:
            shift = normalize_text(section.shift or "")
            score = 100.0 if shift in {"noturno", "noite"} else 0.0 if shift else 50.0
            dimensions.append((score, preferences.prefer_night))
            explanations.append(
                f"Preferencia por noturno aplicada com intensidade {preferences.prefer_night:g}."
            )
        if preferences.avoid_friday > 0:
            score = (
                50.0
                if not section.meetings
                else 0.0
                if any(item.weekday == 4 for item in section.meetings)
                else 100.0
            )
            dimensions.append((score, preferences.avoid_friday))
            explanations.append(
                f"Preferencia de evitar sexta aplicada com intensidade "
                f"{preferences.avoid_friday:g}."
            )
        if preferences.avoid_early_classes > 0:
            score = (
                50.0
                if not section.meetings
                else 100.0
                if all(
                    item.start_time >= preferences.preferred_earliest_start
                    for item in section.meetings
                )
                else 0.0
            )
            dimensions.append((score, preferences.avoid_early_classes))
            explanations.append(
                f"Preferencia por aulas apos "
                f"{preferences.preferred_earliest_start.strftime('%H:%M')} aplicada."
            )
        if preferences.prefer_fewer_campus_days > 0:
            weekdays = {item.weekday for item in section.meetings}
            score = 50.0 if not weekdays else max(100.0 - (len(weekdays) - 1) * 20.0, 0.0)
            dimensions.append((score, preferences.prefer_fewer_campus_days))
            explanations.append(
                f"Turma ocupa {len(weekdays)} dia(s) da semana; "
                "preferencia por menos dias aplicada."
            )
        total_weight = sum(weight for _, weight in dimensions)
        score = sum(value * weight for value, weight in dimensions) / total_weight
        return round(score, 6), explanations

    def _campus_score(
        self,
        section: Section,
        student: StudentProfile,
        preferences: RankingSoftPreferences,
    ) -> tuple[float, str]:
        if preferences.preferred_campuses:
            preferred = {normalize_text(item) for item in preferences.preferred_campuses}
            if section.campus is None:
                return 50.0, "Campus da turma desconhecido; usada nota neutra 50."
            if normalize_text(section.campus) in preferred:
                return 100.0, f"Campus {section.campus} esta entre os campi preferidos."
            return 0.0, f"Campus {section.campus} nao esta entre os campi preferidos."
        if not student.campus or not section.campus:
            return 50.0, "Campus sem comparacao completa; usada nota neutra 50."
        if normalize_text(student.campus) == normalize_text(section.campus):
            return 100.0, f"Campus {section.campus} coincide com a preferencia do aluno."
        return 25.0, f"Campus {section.campus} difere do campus {student.campus}."

    def _section_credits(
        self,
        section: Section,
        student: StudentProfile,
        entry_map: dict[tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject],
    ) -> float | None:
        values: list[float] = []
        for student_course in student.courses:
            entry = entry_map.get((student_course.curriculum_version_id, section.subject_id))
            if entry is not None and entry.credits is not None:
                values.append(float(entry.credits))
        if values:
            return max(values)
        if section.theory_hours is not None or section.practice_hours is not None:
            return float((section.theory_hours or 0) + (section.practice_hours or 0))
        return None

    def _workload_score(
        self,
        section: Section,
        classifications: list[RankingCurriculumClassificationRead],
        config: RankingConfig,
    ) -> tuple[float, str]:
        known_credits = [item.credits for item in classifications if item.credits is not None]
        credits = max(known_credits) if known_credits else None
        if credits is None and (
            section.theory_hours is not None or section.practice_hours is not None
        ):
            credits = float((section.theory_hours or 0) + (section.practice_hours or 0))
        if credits is None:
            return 50.0, "Carga em creditos indisponivel; usada nota neutra 50."
        excess = max(credits - config.preferred_max_subject_credits, 0.0)
        score = max(100.0 - excess * 15.0, 0.0)
        return round(score, 6), (
            f"Carga estimada de {credits:g} creditos comparada ao limite preferido de "
            f"{config.preferred_max_subject_credits:g}."
        )

    def _curriculum_summary(
        self,
        classifications: list[RankingCurriculumClassificationRead],
        config: RankingConfig,
        student: StudentProfile,
    ) -> str:
        strategy = config.course_strategy or student.course_strategy
        values = ", ".join(
            f"{item.course_code}: {item.category.value if item.category else 'sem classificacao'}"
            for item in classifications
        )
        return f"Classificacoes curriculares ({strategy.value}): {values}."
