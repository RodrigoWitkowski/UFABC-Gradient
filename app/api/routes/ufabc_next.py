import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.core.config import get_settings
from app.models.ufabc_next import UfabcNextSyncRun
from app.schemas.ufabc_next import UfabcNextSyncRequest, UfabcNextSyncRunRead
from app.services.ufabc_next import UfabcNextClient, UfabcNextSyncError, UfabcNextSyncService
from app.services.ufabc_next.cache import UfabcNextDatabaseCache

router = APIRouter(prefix="/sync/ufabc-next", tags=["ufabc-next"])


@router.post("", response_model=UfabcNextSyncRunRead, status_code=status.HTTP_201_CREATED)
def sync_ufabc_next(
    payload: UfabcNextSyncRequest,
    db: DatabaseSession,
) -> UfabcNextSyncRunRead:
    settings = get_settings()
    if not settings.ufabc_next_enabled:
        raise HTTPException(status_code=503, detail="integracao com UFABC Next esta desativada")
    client = UfabcNextClient(settings, UfabcNextDatabaseCache(db))
    try:
        run = UfabcNextSyncService(db, client).sync(payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UfabcNextSyncError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": str(exc), "sync_run_id": str(exc.run_id)},
        ) from exc
    finally:
        client.close()
    return UfabcNextSyncRunRead.model_validate(run)


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
