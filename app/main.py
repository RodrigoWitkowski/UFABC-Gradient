from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import courses, imports, rankings, statistics, students, terms, ufabc_next
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.services.official_curricula import import_official_curricula

WEB_DIRECTORY = Path(__file__).parent / "web"
SETTINGS = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    if not getattr(app.state, "skip_startup_curriculum_sync", False):
        with SessionLocal() as session:
            import_official_curricula(session)
            session.commit()
    yield


app = FastAPI(
    title=SETTINGS.app_name,
    version="0.11.0",
    docs_url="/docs" if SETTINGS.api_docs_enabled else None,
    redoc_url="/redoc" if SETTINGS.api_docs_enabled else None,
    openapi_url="/openapi.json" if SETTINGS.api_docs_enabled else None,
    lifespan=lifespan,
)
app.mount("/assets", StaticFiles(directory=WEB_DIRECTORY), name="assets")
app.include_router(imports.router)
app.include_router(terms.router)
app.include_router(courses.router)
app.include_router(students.router)
app.include_router(ufabc_next.router)
app.include_router(statistics.router)
app.include_router(rankings.router)


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(WEB_DIRECTORY / "index.html")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
