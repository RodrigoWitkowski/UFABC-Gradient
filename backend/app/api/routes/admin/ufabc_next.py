import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.models.ufabc_next import UfabcNextSyncRun
from app.schemas.ufabc_next import UfabcNextSyncRunRead

router = APIRouter(
    prefix="/admin/integrations/ufabc-next",
    tags=["admin-ufabc-next"],
)


@router.get("/status", response_model=UfabcNextSyncRunRead)
def get_ufabc_next_sync_status(
    db: DatabaseSession,
    run_id: Annotated[uuid.UUID | None, Query()] = None,
) -> UfabcNextSyncRunRead:
    statement = select(UfabcNextSyncRun)
    if run_id is not None:
        statement = statement.where(UfabcNextSyncRun.id == run_id)
    else:
        statement = statement.order_by(UfabcNextSyncRun.created_at.desc()).limit(1)
    run = db.scalar(statement)
    if run is None:
        raise HTTPException(status_code=404, detail="sincronizacao nao encontrada")
    return UfabcNextSyncRunRead.model_validate(run)
