from collections.abc import Generator

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.main import app


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    database = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(database, "connect")
    def enable_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(database)
    yield database
    Base.metadata.drop_all(database)
    database.dispose()


@pytest.fixture
def session(engine: Engine) -> Generator[Session, None, None]:
    with Session(engine, expire_on_commit=False) as database_session:
        yield database_session


@pytest.fixture(autouse=True)
def disable_startup_curriculum_sync() -> Generator[None, None, None]:
    previous = getattr(app.state, "skip_startup_curriculum_sync", False)
    app.state.skip_startup_curriculum_sync = True
    yield
    app.state.skip_startup_curriculum_sync = previous
