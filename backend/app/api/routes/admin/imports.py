import json
import shutil
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import DatabaseSession
from app.api.serializers import serialize_import_batch
from app.core.config import get_settings
from app.models.imports import ImportBatch
from app.offers import ImportStorage, OfferImporter
from app.schemas.imports import ImportBatchRead

router = APIRouter(prefix="/admin/imports", tags=["admin-imports"])


@router.post("/offers", response_model=ImportBatchRead, status_code=status.HTTP_201_CREATED)
def import_offers(
    db: DatabaseSession,
    file: Annotated[UploadFile, File()],
    term: Annotated[str | None, Form()] = None,
    sheet_name: Annotated[str | None, Form()] = None,
    column_mapping: Annotated[str | None, Form()] = None,
) -> ImportBatchRead:
    try:
        parsed_mapping = json.loads(column_mapping) if column_mapping else None
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="column_mapping deve ser um objeto JSON"
        ) from exc
    if parsed_mapping is not None and not isinstance(parsed_mapping, dict):
        raise HTTPException(status_code=400, detail="column_mapping deve ser um objeto JSON")

    storage = ImportStorage(get_settings().import_storage_path)
    incoming = storage.incoming_path(file.filename or "oferta.xlsx")
    try:
        with incoming.open("wb") as destination:
            shutil.copyfileobj(file.file, destination)
        batch = OfferImporter(db, storage.root).import_path(
            incoming,
            original_filename=file.filename,
            content_type=file.content_type,
            term_code=term,
            sheet_name=sheet_name,
            column_mapping=parsed_mapping,
        )
    finally:
        incoming.unlink(missing_ok=True)
    return serialize_import_batch(batch)


@router.get("/{batch_id}", response_model=ImportBatchRead)
def get_import(batch_id: uuid.UUID, db: DatabaseSession) -> ImportBatchRead:
    batch = db.scalar(
        select(ImportBatch)
        .where(ImportBatch.id == batch_id)
        .options(
            selectinload(ImportBatch.import_file),
            selectinload(ImportBatch.term),
            selectinload(ImportBatch.issues),
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="importacao nao encontrada")
    return serialize_import_batch(batch)
