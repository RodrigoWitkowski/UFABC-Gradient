from __future__ import annotations

import uuid
from dataclasses import dataclass
from random import Random

from app.models.curriculum import CourseCurriculumSubject
from app.models.enums import CurriculumCategory
from app.models.imports import Term
from app.models.offerings import Section
from app.models.students import StudentCourse, StudentProfile
from app.schemas.rankings import (
    EnrollmentPriorityRead,
    LocalPopulationProbabilityConfig,
)
from app.services.enrollment import EnrollmentPriorityEvaluator


@dataclass(frozen=True)
class LocalPopulationProbabilityEstimate:
    probability: float
    observed_population: int
    simulations: int
    summary: str
    favorable_factors: tuple[str, ...]
    risk_factors: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _PopulationCandidate:
    priority_key: tuple[int, int, float, float]
    request_probability: float


class LocalPopulationAdmissionProbabilityService:
    def __init__(self) -> None:
        self.priority_evaluator = EnrollmentPriorityEvaluator()

    def estimate(
        self,
        *,
        section: Section,
        term: Term,
        target_student: StudentProfile,
        target_priority: EnrollmentPriorityRead,
        population_students: list[StudentProfile],
        config: LocalPopulationProbabilityConfig,
        curriculum_entries: dict[tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject],
    ) -> LocalPopulationProbabilityEstimate | None:
        if not config.enabled:
            return None
        seats = section.total_seats
        if seats is None or seats <= 0:
            return None
        if self._is_ineligible(target_student, section.subject_id):
            return LocalPopulationProbabilityEstimate(
                probability=0.0,
                observed_population=0,
                simulations=config.simulations,
                summary="O proprio perfil ja nao e elegivel para esta disciplina.",
                favorable_factors=(),
                risk_factors=("O aluno ja concluiu ou esta cursando a disciplina.",),
                warnings=(
                    "A estimativa local foi zerada porque o proprio perfil ja nao e elegivel.",
                ),
            )

        candidates: list[_PopulationCandidate] = []
        for student in population_students:
            if not student.courses or student.ca is None:
                continue
            if self._is_ineligible(student, section.subject_id):
                continue
            priority = self.priority_evaluator.evaluate(
                section=section,
                term=term,
                student=student,
                curriculum_entries=curriculum_entries,
            )
            request_probability = self._request_probability(
                section=section,
                student=student,
                priority=priority,
                config=config,
                curriculum_entries=curriculum_entries,
            )
            if request_probability <= 0:
                continue
            candidates.append(
                _PopulationCandidate(
                    priority_key=self._priority_key(priority),
                    request_probability=request_probability,
                )
            )

        observed_population = len(candidates) + 1
        if observed_population < config.min_population_size:
            return None

        target_key = self._priority_key(target_priority)
        stronger_candidates = sum(candidate.priority_key > target_key for candidate in candidates)
        probability = self._simulate_probability(
            target_key=target_key,
            seats=seats,
            candidates=candidates,
            simulations=config.simulations,
            seed=(section.id.int ^ target_student.id.int ^ config.simulations) & 0xFFFFFFFF,
        )

        favorable: list[str] = [
            f"Estimativa personalizada baseada em {observed_population} perfis locais elegiveis.",
        ]
        risks: list[str] = []
        if stronger_candidates < seats:
            favorable.append(
                "Na base local observada, menos perfis tem prioridade superior do que vagas."
            )
        else:
            risks.append(
                f"Na base local observada, {stronger_candidates} perfis elegiveis "
                "tem prioridade superior."
            )
        if observed_population < max(config.min_population_size * 2, 25):
            risks.append("A base local ainda e pequena para estabilizar bem a estimativa.")

        warnings = (
            "Modelo local usa somente perfis cadastrados no app e propensao estimada "
            "por categoria, vinculo e turno.",
            "Esta etapa ainda nao usa demanda observada da matricula "
            "nem IDs reais de solicitantes.",
        )
        return LocalPopulationProbabilityEstimate(
            probability=probability,
            observed_population=observed_population,
            simulations=config.simulations,
            summary=(
                f"Estimativa personalizada baseada em {observed_population} "
                "perfis locais elegiveis."
            ),
            favorable_factors=tuple(favorable),
            risk_factors=tuple(risks),
            warnings=warnings,
        )

    @staticmethod
    def _is_ineligible(student: StudentProfile, subject_id: uuid.UUID) -> bool:
        if any(item.subject_id == subject_id for item in student.completed_subjects):
            return True
        if any(item.subject_id == subject_id for item in student.in_progress_subjects):
            return True
        return False

    def _request_probability(
        self,
        *,
        section: Section,
        student: StudentProfile,
        priority: EnrollmentPriorityRead,
        config: LocalPopulationProbabilityConfig,
        curriculum_entries: dict[tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject],
    ) -> float:
        base_probability = config.unclassified_request_probability
        for course in student.courses:
            category = self._category_for_course(section, course, curriculum_entries)
            base_probability = max(
                base_probability,
                self._category_probability(category, config),
            )
        if priority.course_priority is True:
            base_probability *= config.priority_affiliation_multiplier
        if priority.same_shift is True:
            base_probability *= config.same_shift_multiplier
        return min(max(base_probability, 0.0), config.max_request_probability)

    @staticmethod
    def _category_for_course(
        section: Section,
        course: StudentCourse,
        curriculum_entries: dict[tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject],
    ) -> CurriculumCategory | None:
        entry = curriculum_entries.get((course.curriculum_version_id, section.subject_id))
        if entry is not None:
            return entry.category
        return course.curriculum_version.unlisted_subject_category

    @staticmethod
    def _category_probability(
        category: CurriculumCategory | None,
        config: LocalPopulationProbabilityConfig,
    ) -> float:
        if category == CurriculumCategory.MANDATORY:
            return config.mandatory_request_probability
        if category == CurriculumCategory.LIMITED:
            return config.limited_request_probability
        if category == CurriculumCategory.FREE:
            return config.free_request_probability
        return config.unclassified_request_probability

    @staticmethod
    def _priority_key(priority: EnrollmentPriorityRead) -> tuple[int, int, float, float]:
        return (
            int(priority.course_priority is True),
            int(priority.same_shift is True),
            priority.cp if priority.cp is not None else -1.0,
            priority.ca if priority.ca is not None else -1.0,
        )

    @staticmethod
    def _simulate_probability(
        *,
        target_key: tuple[int, int, float, float],
        seats: int,
        candidates: list[_PopulationCandidate],
        simulations: int,
        seed: int,
    ) -> float:
        rng = Random(seed)
        admitted = 0
        for _ in range(simulations):
            requesters: list[tuple[tuple[int, int, float, float], float, bool]] = [
                (target_key, rng.random(), True)
            ]
            for candidate in candidates:
                if rng.random() < candidate.request_probability:
                    requesters.append((candidate.priority_key, rng.random(), False))
            if len(requesters) <= seats:
                admitted += 1
                continue
            requesters.sort(key=lambda item: (item[0], item[1]), reverse=True)
            if any(is_target for _key, _tie_break, is_target in requesters[:seats]):
                admitted += 1
        return admitted / simulations
