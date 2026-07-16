from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import courses, imports, students, terms, ufabc_next
from app.core.config import get_settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


app = FastAPI(
    title=get_settings().app_name,
    version="0.3.0",
    lifespan=lifespan,
)
app.include_router(imports.router)
app.include_router(terms.router)
app.include_router(courses.router)
app.include_router(students.router)
app.include_router(ufabc_next.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
