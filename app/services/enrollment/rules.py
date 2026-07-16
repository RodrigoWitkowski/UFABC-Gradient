from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from app.models.curriculum import CourseCurriculumSubject
from app.models.enums import CurriculumCategory
from app.models.imports import Term
from app.models.offerings import Section
from app.models.students import StudentCourse, StudentProfile
from app.schemas.rankings import (
    EnrollmentPriorityCriterionRead,
    EnrollmentPriorityRead,
)
from app.services.normalization.text import normalize_text

INTERDISCIPLINARY_COURSE_CODES = {"BCT", "BCH", "LCH", "LCNE"}


@dataclass(frozen=True)
class EnrollmentRuleVersion:
    code: str
    effective_year: int
    effective_term: int
    source_url: str

    @property
    def effective_from(self) -> str:
        return f"{self.effective_year}:{self.effective_term}"


RULES = (
    EnrollmentRuleVersion(
        code="consepe-260-2023",
        effective_year=2024,
        effective_term=1,
        source_url=(
            "https://www.ufabc.edu.br/images/consepe/resolucoes/"
            "resoluo_260_-_estabelece_normas_e_critrios_para_a_solicitao_e_"
            "cancelamento_de_matrculas_em_disciplinas_da_grad_revoga_e_subst_"
            "131_n_202_e_n_219_assinada.pdf"
        ),
    ),
)


def rule_for_term(term: Term) -> EnrollmentRuleVersion | None:
    applicable = [
        rule
        for rule in RULES
        if (term.year, term.term_number) >= (rule.effective_year, rule.effective_term)
    ]
    return applicable[-1] if applicable else None


class EnrollmentPriorityEvaluator:
    def evaluate(
        self,
        *,
        section: Section,
        term: Term,
        student: StudentProfile,
        curriculum_entries: Mapping[
            tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject
        ],
    ) -> EnrollmentPriorityRead:
        rule = rule_for_term(term)
        offering_courses = [item.course for item in section.course_links]
        offering_course = offering_courses[0] if len(offering_courses) == 1 else None
        offering_code = offering_course.code if offering_course is not None else None
        offering_type = self._offering_type(offering_code)
        ingress_course = self._ingress_course(student)

        missing_data: list[str] = []
        warnings: list[str] = []
        if rule is None:
            warnings.append("Nao ha regra de matricula cadastrada para este quadrimestre.")
        if not offering_courses:
            missing_data.append("curso ofertante da turma")
        elif len(offering_courses) > 1:
            missing_data.append("curso ofertante unico da turma")
        if offering_type == "unknown":
            missing_data.append("tipo do curso ofertante")

        course_priority: bool | None = None
        pool = "unknown"
        cp_course: StudentCourse | None = None
        course_explanation = "Nao foi possivel avaliar o primeiro criterio."
        course_status = "unknown"

        if offering_type == "interdisciplinary":
            pool = "general"
            cp_course = ingress_course
            matching_course = self._course_by_code(student, offering_code)
            category = self._category(section, matching_course, curriculum_entries)
            if matching_course is None:
                course_priority = False
                course_status = "unfavorable"
                course_explanation = (
                    f"O perfil nao possui vinculo com o curso de ingresso {offering_code}."
                )
            elif category is None:
                missing_data.append(f"categoria da disciplina em {offering_code}")
                course_explanation = (
                    f"A categoria da disciplina em {offering_code} nao esta disponivel."
                )
            else:
                course_priority = category == CurriculumCategory.MANDATORY
                course_status = "favorable" if course_priority else "unfavorable"
                course_explanation = (
                    f"A disciplina e {category.value} em {offering_code}; apenas obrigatorias "
                    "satisfazem o primeiro criterio para curso de ingresso."
                )
        elif offering_type == "specific":
            matching_course = self._course_by_code(student, offering_code)
            category = self._category(section, matching_course, curriculum_entries)
            is_priority_category = category in {
                CurriculumCategory.MANDATORY,
                CurriculumCategory.LIMITED,
            }
            course_priority = matching_course is not None and is_priority_category
            if course_priority:
                pool = "specific_linked"
                cp_course = matching_course
                course_status = "favorable"
                course_explanation = (
                    f"O perfil tem vinculo com {offering_code} e a disciplina e "
                    f"{category.value if category is not None else 'sem classificacao'}; "
                    "concorre no grupo vinculado."
                )
            else:
                pool = "specific_non_linked_20_percent"
                cp_course = ingress_course
                course_status = "informational"
                category_text = category.value if category is not None else "sem classificacao"
                course_explanation = (
                    f"Sem vinculo prioritario para esta disciplina em {offering_code} "
                    f"({category_text}); concorre na reserva de 20% para nao vinculados."
                )

        same_shift = self._same_shift(student.admission_shift, section.shift)
        if same_shift is None:
            missing_data.append("comparacao entre turno de ingresso e turno da turma")
            shift_status = "unknown"
            shift_explanation = "Turno do perfil ou da turma nao informado."
        elif same_shift:
            shift_status = "favorable"
            shift_explanation = "O turno de ingresso coincide com o turno da turma."
        else:
            shift_status = "unfavorable"
            shift_explanation = "O turno de ingresso nao coincide com o turno da turma."

        cp = float(cp_course.cp) if cp_course is not None and cp_course.cp is not None else None
        if cp is None:
            missing_data.append("CP aplicavel")
        ca = float(student.ca) if student.ca is not None else None
        if ca is None:
            missing_data.append("CA")

        criteria = [
            EnrollmentPriorityCriterionRead(
                order=1,
                code="course",
                value=course_priority,
                status=course_status,
                explanation=course_explanation,
            ),
            EnrollmentPriorityCriterionRead(
                order=2,
                code="shift",
                value=same_shift,
                status=shift_status,
                explanation=shift_explanation,
            ),
            EnrollmentPriorityCriterionRead(
                order=3,
                code="cp",
                value=cp,
                status="informational" if cp is not None else "unknown",
                explanation=(
                    f"CP {cp:g}, comparado em ordem decrescente dentro dos grupos anteriores."
                    if cp is not None
                    else "CP aplicavel nao informado."
                ),
            ),
            EnrollmentPriorityCriterionRead(
                order=4,
                code="ca",
                value=ca,
                status="informational" if ca is not None else "unknown",
                explanation=(
                    f"CA {ca:g}, usado depois do CP."
                    if ca is not None
                    else "CA nao informado."
                ),
            ),
        ]
        favorable = [item.explanation for item in criteria if item.status == "favorable"]
        risks = [item.explanation for item in criteria if item.status == "unfavorable"]
        warnings.extend(
            [
                "Campus nao faz parte da ordem de classificacao da primeira fase.",
                "CR e IK nao fazem parte da ordem curso, turno, CP e CA.",
                "A posicao relativa depende dos dados dos outros solicitantes.",
            ]
        )
        return EnrollmentPriorityRead(
            rule_version=rule.code if rule is not None else None,
            rule_effective_from=rule.effective_from if rule is not None else None,
            rule_source_url=rule.source_url if rule is not None else None,
            offering_course_code=offering_code,
            offering_course_type=offering_type,
            competition_pool=pool,
            course_priority=course_priority,
            same_shift=same_shift,
            cp=cp,
            ca=ca,
            criteria=criteria,
            favorable_factors=favorable,
            risk_factors=risks,
            missing_data=list(dict.fromkeys(missing_data)),
            warnings=warnings,
        )

    @staticmethod
    def _offering_type(code: str | None) -> str:
        if code is None:
            return "unknown"
        return "interdisciplinary" if code in INTERDISCIPLINARY_COURSE_CODES else "specific"

    @staticmethod
    def _course_by_code(student: StudentProfile, code: str | None) -> StudentCourse | None:
        if code is None:
            return None
        return next((item for item in student.courses if item.course.code == code), None)

    @staticmethod
    def _ingress_course(student: StudentProfile) -> StudentCourse | None:
        matches = [
            item for item in student.courses if item.course.code in INTERDISCIPLINARY_COURSE_CODES
        ]
        return next((item for item in matches if item.is_primary), matches[0] if matches else None)

    @staticmethod
    def _category(
        section: Section,
        student_course: StudentCourse | None,
        entries: Mapping[tuple[uuid.UUID, uuid.UUID], CourseCurriculumSubject],
    ) -> CurriculumCategory | None:
        if student_course is None:
            return None
        entry = entries.get((student_course.curriculum_version_id, section.subject_id))
        if entry is not None:
            return entry.category
        return student_course.curriculum_version.unlisted_subject_category

    @staticmethod
    def _same_shift(student_shift: str | None, section_shift: str | None) -> bool | None:
        if not student_shift or not section_shift:
            return None
        return normalize_text(student_shift) == normalize_text(section_shift)
