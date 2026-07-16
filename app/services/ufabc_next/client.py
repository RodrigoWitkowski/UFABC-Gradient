from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import Settings
from app.services.ufabc_next.cache import UfabcNextDatabaseCache

logger = logging.getLogger(__name__)
PRIVATE_RESPONSE_KEYS = {
    "__v",
    "alunos_matriculados",
    "email",
    "externalKey",
    "login",
    "ra",
    "siape",
}


class UfabcNextError(RuntimeError):
    pass


class UfabcNextDisabledError(UfabcNextError):
    pass


class UfabcNextRequestLimitError(UfabcNextError):
    pass


class UfabcNextResponseError(UfabcNextError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class UfabcNextClient:
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        settings: Settings,
        cache: UfabcNextDatabaseCache,
        *,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.cache = cache
        self.sleep = sleep
        self.monotonic = monotonic
        self.remote_requests = 0
        self.cache_hits = 0
        self.request_log: list[dict[str, Any]] = []
        self._last_request_at: float | None = None
        self._owns_client = http_client is None
        self.http = http_client or httpx.Client(
            base_url=settings.ufabc_next_base_url.rstrip("/"),
            timeout=settings.ufabc_next_timeout_seconds,
            headers={"User-Agent": "ufabc-class-ranking/0.6-experiment"},
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self.http.close()

    def get_components(
        self,
        season: str,
        *,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            "/entities/components",
            params={"season": season},
            ttl_seconds=self.settings.ufabc_next_component_cache_seconds,
            force_refresh=force_refresh,
            sanitizer=self._sanitize_components,
        )
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise UfabcNextResponseError("resposta de componentes possui formato invalido")
        return payload

    def get_teacher_reviews(
        self,
        teacher_id: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        payload = self._get_json(
            f"/entities/teachers/reviews/{teacher_id}",
            params={},
            ttl_seconds=self.settings.ufabc_next_review_cache_seconds,
            force_refresh=force_refresh,
            sanitizer=self._sanitize_private_fields,
        )
        if not isinstance(payload, dict):
            raise UfabcNextResponseError("resposta de reviews do professor possui formato invalido")
        return payload

    def get_subject_reviews(
        self,
        subject_id: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        payload = self._get_json(
            f"/entities/subjects/reviews/{subject_id}",
            params={},
            ttl_seconds=self.settings.ufabc_next_review_cache_seconds,
            force_refresh=force_refresh,
            sanitizer=self._sanitize_private_fields,
        )
        if not isinstance(payload, dict):
            raise UfabcNextResponseError(
                "resposta de reviews da disciplina possui formato invalido"
            )
        return payload

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any],
        ttl_seconds: int,
        force_refresh: bool,
        sanitizer: Callable[[Any], Any],
    ) -> Any:
        if not self.settings.ufabc_next_enabled:
            raise UfabcNextDisabledError("integracao com UFABC Next esta desativada")
        request_key = self._request_key(path, params)
        if not force_refresh and ttl_seconds > 0:
            cached = self.cache.get(request_key)
            if cached is not None:
                self.cache_hits += 1
                return sanitizer(cached)

        last_error: Exception | None = None
        for attempt in range(self.settings.ufabc_next_max_retries + 1):
            if self.remote_requests >= self.settings.ufabc_next_max_requests_per_sync:
                raise UfabcNextRequestLimitError(
                    "limite local de chamadas ao UFABC Next atingido; "
                    "a sincronizacao foi interrompida por seguranca"
                )
            self._wait_for_rate_limit()
            try:
                response = self.http.get(path, params=params)
                self.remote_requests += 1
            except httpx.RequestError as exc:
                last_error = exc
                self.request_log.append({"path": path, "status_code": None, "error": str(exc)})
                if attempt >= self.settings.ufabc_next_max_retries:
                    break
                self._backoff(attempt)
                continue

            logger.info(
                "ufabc_next_response",
                extra={
                    "provider": "ufabc_next",
                    "path": path,
                    "status_code": response.status_code,
                },
            )
            request_record: dict[str, Any] = {
                "path": path,
                "status_code": response.status_code,
            }
            self.request_log.append(request_record)
            if response.status_code in self.RETRYABLE_STATUS_CODES:
                last_error = UfabcNextResponseError(
                    f"UFABC Next retornou HTTP {response.status_code}",
                    status_code=response.status_code,
                )
                if attempt >= self.settings.ufabc_next_max_retries:
                    break
                self._backoff(attempt, response)
                continue
            if response.is_error:
                raise UfabcNextResponseError(
                    f"UFABC Next retornou HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise UfabcNextResponseError("UFABC Next retornou JSON invalido") from exc
            payload = sanitizer(payload)
            request_record.update(self._response_summary(payload))
            if ttl_seconds > 0:
                self.cache.put(
                    request_key=request_key,
                    path=path,
                    params=params,
                    status_code=response.status_code,
                    response_body=payload,
                    ttl_seconds=ttl_seconds,
                )
            return payload

        raise UfabcNextResponseError(
            f"UFABC Next indisponivel apos tentativas limitadas: {last_error}"
        ) from last_error

    def _wait_for_rate_limit(self) -> None:
        now = self.monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            remaining = self.settings.ufabc_next_min_interval_seconds - elapsed
            if remaining > 0:
                self.sleep(remaining)
        self._last_request_at = self.monotonic()

    def _backoff(self, attempt: int, response: httpx.Response | None = None) -> None:
        retry_after = response.headers.get("retry-after") if response is not None else None
        if retry_after is not None:
            try:
                self.sleep(max(float(retry_after), 0))
                return
            except ValueError:
                pass
        self.sleep(self.settings.ufabc_next_backoff_seconds * (2**attempt))

    @staticmethod
    def _request_key(path: str, params: dict[str, Any]) -> str:
        canonical = json.dumps(
            {"path": path, "params": params},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _response_summary(payload: Any) -> dict[str, int]:
        if isinstance(payload, list):
            return {"items_returned": len(payload)}
        if isinstance(payload, dict):
            general = payload.get("general")
            if isinstance(general, dict) and isinstance(general.get("count"), int):
                return {"sample_size": general["count"]}
        return {}

    @classmethod
    def _sanitize_components(cls, payload: Any) -> Any:
        if not isinstance(payload, list):
            return payload
        sanitized = []
        for item in payload:
            if not isinstance(item, dict):
                sanitized.append(item)
                continue
            enrolled = item.get("alunos_matriculados")
            existing_count = item.get("enrolled_count")
            clean_item = {
                key: cls._sanitize_private_fields(value)
                for key, value in item.items()
                if key != "alunos_matriculados"
            }
            clean_item["enrolled_count"] = (
                existing_count
                if isinstance(existing_count, int)
                else len(enrolled)
                if isinstance(enrolled, list)
                else 0
            )
            sanitized.append(clean_item)
        return sanitized

    @classmethod
    def _sanitize_private_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._sanitize_private_fields(item)
                for key, item in value.items()
                if key not in PRIVATE_RESPONSE_KEYS
            }
        if isinstance(value, list):
            return [cls._sanitize_private_fields(item) for item in value]
        return value
