"""Student domain package."""

from importlib import import_module
from typing import Any

_HISTORY_EXPORTS = {
    "HistoryEntry",
    "HistoryPdfError",
    "HistoryPdfParser",
    "ParsedStudentHistory",
    "StudentHistoryConflictError",
    "StudentHistoryService",
}

_SERVICE_EXPORTS = {
    "StudentAcademicDataLockedError",
    "StudentNotFoundError",
    "StudentService",
}

__all__ = sorted(_HISTORY_EXPORTS | _SERVICE_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _HISTORY_EXPORTS:
        return getattr(import_module("app.students.history"), name)
    if name in _SERVICE_EXPORTS:
        return getattr(import_module("app.students.service"), name)
    raise AttributeError(name)
