import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DatabaseSession
from app.ranking import RankingNotFoundError, RankingService
from app.schemas.rankings import (
    RankingRead,
    SectionRankingRequest,
)
from app.students import StudentNotFoundError

router = APIRouter(prefix="/rankings", tags=["rankings"])


@router.post("/sections", response_model=RankingRead, status_code=status.HTTP_201_CREATED)
def rank_sections(payload: SectionRankingRequest, db: DatabaseSession) -> RankingRead:
    service = RankingService(db)
    try:
        ranking = service.create_ranking(payload)
        ranking_id = ranking.id
        db.commit()
        return service.serialize(service.get_ranking(ranking_id))
    except StudentNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{ranking_id}", response_model=RankingRead)
def get_ranking(ranking_id: uuid.UUID, db: DatabaseSession) -> RankingRead:
    service = RankingService(db)
    try:
        return service.serialize(service.get_ranking(ranking_id))
    except RankingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
