import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DatabaseSession
from app.api.serializers import serialize_student
from app.schemas.students import (
    AcademicProfileUpdate,
    StudentCreate,
    StudentHistoryImportRead,
    StudentRead,
    StudentSubjectClassificationsRead,
)
from app.services.student_history import (
    HistoryPdfError,
    HistoryPdfParser,
    StudentHistoryConflictError,
    StudentHistoryService,
)
from app.services.students import StudentNotFoundError, StudentService

router = APIRouter(prefix="/students", tags=["students"])


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
def create_student(payload: StudentCreate, db: DatabaseSession) -> StudentRead:
    service = StudentService(db)
    try:
        profile = service.create_student(payload)
        db.commit()
        return serialize_student(service.get_student(profile.id))
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="RA ja cadastrado") from exc


@router.post("/history/pdf", response_model=StudentHistoryImportRead)
async def import_student_history_pdf(
    db: DatabaseSession,
    file: Annotated[UploadFile, File(description="Historico Escolar emitido pelo SIGAA")],
    student_id: Annotated[uuid.UUID | None, Form()] = None,
) -> StudentHistoryImportRead:
    content = await file.read()
    await file.close()
    try:
        parsed = HistoryPdfParser().parse(content)
        result = StudentHistoryService(db).import_pdf(
            parsed=parsed,
            content=content,
            original_filename=file.filename or "historico.pdf",
            student_id=student_id,
        )
        db.commit()
        student = serialize_student(StudentService(db).get_student(result.profile.id))
        return StudentHistoryImportRead(
            student=student,
            original_filename=result.history_import.original_filename,
            sha256=result.history_import.sha256,
            issued_at=result.history_import.issued_at,
            imported_at=result.history_import.imported_at,
            replaced_existing=result.replaced_existing,
            completed_count=result.completed_count,
            completed_attempt_count=result.completed_attempt_count,
            in_progress_count=result.in_progress_count,
            ignored_attempt_count=result.ignored_attempt_count,
            warnings=result.warnings,
        )
    except StudentNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HistoryPdfError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (StudentHistoryConflictError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{student_id}", response_model=StudentRead)
def get_student(student_id: uuid.UUID, db: DatabaseSession) -> StudentRead:
    try:
        return serialize_student(StudentService(db).get_student(student_id))
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{student_id}/academic-profile", response_model=StudentRead)
def update_academic_profile(
    student_id: uuid.UUID,
    payload: AcademicProfileUpdate,
    db: DatabaseSession,
) -> StudentRead:
    service = StudentService(db)
    try:
        service.update_academic_profile(student_id, payload)
        db.commit()
        return serialize_student(service.get_student(student_id))
    except StudentNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/{student_id}/subjects/{subject_code}/classifications",
    response_model=StudentSubjectClassificationsRead,
)
def get_subject_classifications(
    student_id: uuid.UUID,
    subject_code: str,
    db: DatabaseSession,
) -> StudentSubjectClassificationsRead:
    try:
        return StudentService(db).classify_subject(student_id, subject_code)
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
