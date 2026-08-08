import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DatabaseSession
from app.ranking import RankingNotFoundError, RankingService
from app.schemas.rankings import RankingRead, RankingRerankRequest
from app.students import StudentNotFoundError

router = APIRouter(prefix="/admin/rankings", tags=["admin-rankings"])


@router.post(
    "/{ranking_id}/rerank",
    response_model=RankingRead,
    status_code=status.HTTP_201_CREATED,
)
def rerank_sections(
    ranking_id: uuid.UUID,
    payload: RankingRerankRequest,
    db: DatabaseSession,
) -> RankingRead:
    service = RankingService(db)
    try:
        ranking = service.rerank(ranking_id, payload)
        new_ranking_id = ranking.id
        db.commit()
        return service.serialize(service.get_ranking(new_ranking_id))
    except RankingNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (StudentNotFoundError, ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
