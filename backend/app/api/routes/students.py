import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DatabaseSession
from app.api.serializers import serialize_student
from app.schemas.students import StudentHistoryImportRead, StudentRead
from app.students import (
    HistoryPdfError,
    HistoryPdfParser,
    StudentHistoryConflictError,
    StudentHistoryService,
    StudentNotFoundError,
    StudentService,
)

router = APIRouter(prefix="/students", tags=["students"])


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
