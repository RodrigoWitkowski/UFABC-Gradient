from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.models.statistics import StatisticsBuild
from app.schemas.statistics import (
    StatisticsBuildRead,
    StatisticsBuildRequest,
    TeacherStatisticsEvaluationRead,
    TeacherStatisticsEvaluationRequest,
)
from app.teachers import StatisticsBuilder, TeacherStatisticsEvaluator

router = APIRouter(prefix="/admin/statistics", tags=["admin-statistics"])


@router.post(
    "/rebuild",
    response_model=StatisticsBuildRead,
    status_code=status.HTTP_201_CREATED,
)
def rebuild_statistics(
    payload: StatisticsBuildRequest,
    db: DatabaseSession,
) -> StatisticsBuildRead:
    try:
        build = StatisticsBuilder(db).rebuild(
            prior_weight=payload.prior_weight,
            grade_weights=payload.grade_weights,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StatisticsBuildRead.model_validate(build)


@router.get("/status", response_model=StatisticsBuildRead)
def get_statistics_status(db: DatabaseSession) -> StatisticsBuildRead:
    build = db.scalar(select(StatisticsBuild).order_by(StatisticsBuild.computed_at.desc()).limit(1))
    if build is None:
        raise HTTPException(status_code=404, detail="estatisticas ainda nao foram calculadas")
    return StatisticsBuildRead.model_validate(build)


@router.post("/teachers/evaluate", response_model=TeacherStatisticsEvaluationRead)
def evaluate_teacher_statistics(
    payload: TeacherStatisticsEvaluationRequest,
    db: DatabaseSession,
) -> TeacherStatisticsEvaluationRead:
    try:
        return TeacherStatisticsEvaluator(db).evaluate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
