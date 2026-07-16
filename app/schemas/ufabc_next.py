import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ExternalSyncStatus


class UfabcNextSyncRequest(BaseModel):
    season: str = Field(pattern=r"^[0-9]{4}:[1-3]$")
    include_teacher_reviews: bool = False
    include_subject_reviews: bool = False
    review_limit: int = Field(default=25, ge=1, le=25)
    force_refresh: bool = False


class UfabcNextSyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    season: str
    status: ExternalSyncStatus
    include_teacher_reviews: bool
    include_subject_reviews: bool
    force_refresh: bool
    started_at: datetime
    finished_at: datetime | None
    remote_requests: int
    cache_hits: int
    components_received: int
    components_matched: int
    components_unmatched: int
    teacher_reviews_synced: int
    subject_reviews_synced: int
    request_log: list[dict[str, Any]]
    warnings: list[str]
    error_message: str | None
