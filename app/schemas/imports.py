import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ImportIssueLevel, ImportStatus


class ImportIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    level: ImportIssueLevel
    code: str
    row_number: int | None
    field: str | None
    message: str
    raw_data: dict[str, Any] | None


class ImportBatchRead(BaseModel):
    id: uuid.UUID
    status: ImportStatus
    term: str | None
    original_filename: str
    sha256: str
    source_sheet: str | None
    total_rows: int
    imported_rows: int
    invalid_rows: int
    warning_count: int
    added_sections: int
    changed_sections: int
    removed_sections: int
    comparison_batch_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    issues: list[ImportIssueRead]
