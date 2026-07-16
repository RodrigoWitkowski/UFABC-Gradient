from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ufabc_next import UfabcNextCacheEntry


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class UfabcNextDatabaseCache:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, request_key: str) -> Any | None:
        entry = self.session.scalar(
            select(UfabcNextCacheEntry).where(UfabcNextCacheEntry.request_key == request_key)
        )
        if entry is None:
            return None
        if entry.expires_at <= utc_now_naive():
            self.session.delete(entry)
            self.session.flush()
            return None
        return entry.response_body

    def put(
        self,
        *,
        request_key: str,
        path: str,
        params: dict[str, Any],
        status_code: int,
        response_body: Any,
        ttl_seconds: int,
    ) -> None:
        now = utc_now_naive()
        entry = self.session.scalar(
            select(UfabcNextCacheEntry).where(UfabcNextCacheEntry.request_key == request_key)
        )
        if entry is None:
            entry = UfabcNextCacheEntry(request_key=request_key)
            self.session.add(entry)
        entry.path = path
        entry.params = params
        entry.status_code = status_code
        entry.response_body = response_body
        entry.fetched_at = now
        entry.expires_at = now + timedelta(seconds=ttl_seconds)
        self.session.flush()
