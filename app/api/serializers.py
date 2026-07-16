from decimal import Decimal

from app.models.curriculum import CurriculumVersion
from app.models.imports import ImportBatch
from app.models.offerings import Section
from app.models.students import StudentProfile
from app.schemas.curriculum import CurriculumRead
from app.schemas.imports import ImportBatchRead, ImportIssueRead
from app.schemas.offerings import SectionRead
from app.schemas.students import StudentRead


def serialize_import_batch(batch: ImportBatch) -> ImportBatchRead:
    return ImportBatchRead(
        id=batch.id,
        status=batch.status,
        term=batch.term.code if batch.term else None,
        original_filename=batch.import_file.original_filename,
        sha256=batch.import_file.sha256,
        source_sheet=batch.source_sheet,
        total_rows=batch.total_rows,
        imported_rows=batch.imported_rows,
        invalid_rows=batch.invalid_rows,
        warning_count=batch.warning_count,
        added_sections=batch.added_sections,
        changed_sections=batch.changed_sections,
        removed_sections=batch.removed_sections,
        comparison_batch_id=batch.comparison_batch_id,
        started_at=batch.started_at,
        finished_at=batch.finished_at,
        issues=[ImportIssueRead.model_validate(issue) for issue in batch.issues],
    )


def serialize_section(section: Section) -> SectionRead:
    return SectionRead.model_validate(
        {
            "id": section.id,
            "code": section.code,
            "class_group": section.class_group,
            "display_name": section.display_name,
            "campus": section.campus,
            "shift": section.shift,
            "total_seats": section.total_seats,
            "reserved_seats": section.reserved_seats,
            "workload_code": section.workload_code,
            "is_active": section.is_active,
            "subject": {
                "id": section.subject.id,
                "code": section.subject.code,
                "name": section.subject.name,
            },
            "teachers": [
                {
                    "id": item.teacher.id,
                    "name": item.teacher.canonical_name,
                    "role": item.role,
                    "position": item.position,
                }
                for item in section.teachers
            ],
            "meetings": [
                {
                    "id": item.id,
                    "weekday": item.weekday,
                    "start_time": item.start_time,
                    "end_time": item.end_time,
                    "campus": item.campus,
                    "classroom": item.classroom,
                    "frequency": item.frequency,
                    "meeting_type": item.meeting_type,
                }
                for item in section.meetings
            ],
        }
    )


def serialize_curriculum(curriculum: CurriculumVersion) -> CurriculumRead:
    return CurriculumRead.model_validate(
        {
            "id": curriculum.id,
            "course": {
                "id": curriculum.course.id,
                "code": curriculum.course.code,
                "name": curriculum.course.name,
                "source": curriculum.course.source,
            },
            "version": curriculum.version,
            "admission_year_start": curriculum.admission_year_start,
            "admission_year_end": curriculum.admission_year_end,
            "valid_from": curriculum.valid_from,
            "valid_until": curriculum.valid_until,
            "unlisted_subject_category": curriculum.unlisted_subject_category,
            "metadata": curriculum.metadata_,
            "subjects": [
                {
                    "subject_id": entry.subject.id,
                    "code": entry.subject.code,
                    "name": entry.subject.name,
                    "category": entry.category,
                    "category_source": entry.category_source,
                    "ideal_term": entry.ideal_term,
                    "recommended_term": entry.recommended_term,
                    "credits": (
                        entry.credits.quantize(Decimal("0.01"))
                        if entry.credits is not None
                        else None
                    ),
                    "metadata": entry.metadata_,
                }
                for entry in curriculum.subjects
            ],
            "requirements": [
                {
                    "category": item.category,
                    "minimum_credits": (
                        item.minimum_credits.quantize(Decimal("0.01"))
                        if item.minimum_credits is not None
                        else None
                    ),
                    "minimum_subjects": item.minimum_subjects,
                    "metadata": item.metadata_,
                }
                for item in curriculum.requirements
            ],
        }
    )


def serialize_student(profile: StudentProfile) -> StudentRead:
    preferences = profile.preferences
    return StudentRead.model_validate(
        {
            "id": profile.id,
            "ra": profile.ra,
            "display_name": profile.display_name,
            "admission_year": profile.admission_year,
            "admission_shift": profile.admission_shift,
            "campus": profile.campus,
            "cr": profile.cr,
            "ca": profile.ca,
            "max_quarter_credits": profile.max_quarter_credits,
            "accumulated_credits": profile.accumulated_credits,
            "course_strategy": profile.course_strategy,
            "courses": [
                {
                    "id": item.id,
                    "course_id": item.course.id,
                    "course_code": item.course.code,
                    "course_name": item.course.name,
                    "curriculum_version_id": item.curriculum_version.id,
                    "curriculum_version": item.curriculum_version.version,
                    "is_primary": item.is_primary,
                    "weight": item.weight,
                    "cp": item.cp,
                    "ik": item.ik,
                }
                for item in profile.courses
            ],
            "completed_subjects": [
                {
                    "id": item.id,
                    "subject_id": item.subject.id,
                    "code": item.subject.code,
                    "name": item.subject.name,
                    "term": item.term.code if item.term else None,
                    "grade": item.grade,
                    "credits": item.credits,
                    "metadata": item.metadata_,
                }
                for item in profile.completed_subjects
            ],
            "in_progress_subjects": [
                {
                    "id": item.id,
                    "subject_id": item.subject.id,
                    "code": item.subject.code,
                    "name": item.subject.name,
                    "term": item.term.code if item.term else None,
                }
                for item in profile.in_progress_subjects
            ],
            "preferences": {
                "hard_constraints": preferences.hard_constraints if preferences else {},
                "soft_preferences": preferences.soft_preferences if preferences else {},
            },
        }
    )
