from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import rankings, students, terms
from app.api.routes.admin import curricula, imports, statistics, ufabc_next
from app.api.routes.admin import rankings as admin_rankings
from app.api.routes.admin import students as admin_students
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.services.official_curricula import import_official_curricula

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIRECTORY = PROJECT_ROOT / "frontend"
FRONTEND_ASSETS_DIRECTORY = FRONTEND_DIRECTORY / "assets"
FRONTEND_SOURCE_DIRECTORY = FRONTEND_DIRECTORY / "src"
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
app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIRECTORY), name="assets")
app.mount("/src", StaticFiles(directory=FRONTEND_SOURCE_DIRECTORY), name="frontend-src")
app.include_router(imports.router)
app.include_router(terms.router)
app.include_router(students.router)
app.include_router(rankings.router)
app.include_router(curricula.router)
app.include_router(admin_students.router)
app.include_router(statistics.router)
app.include_router(ufabc_next.router)
app.include_router(admin_rankings.router)


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(FRONTEND_DIRECTORY / "index.html")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
