import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DatabaseSession
from app.api.serializers import serialize_student
from app.schemas.students import (
    AcademicProfileUpdate,
    StudentCreate,
    StudentRead,
    StudentSubjectClassificationsRead,
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
