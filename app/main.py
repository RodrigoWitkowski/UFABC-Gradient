from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import courses, imports, rankings, statistics, students, terms, ufabc_next
from app.core.config import get_settings
from app.core.logging import configure_logging

WEB_DIRECTORY = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


app = FastAPI(
    title=get_settings().app_name,
    version="0.9.0",
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
