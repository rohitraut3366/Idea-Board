import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from idea_board.database import create_database_engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://idea_board:idea_board_local@127.0.0.1:55432/idea_board"
)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    admin_url = make_url(os.getenv("IDEA_BOARD_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL))
    admin_url = admin_url.set(drivername="postgresql+psycopg")
    database_name = f"idea_board_test_{uuid4().hex}"
    admin_engine = create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 3},
    )
    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

        test_url = admin_url.set(database=database_name).render_as_string(hide_password=False)
        migration_engine = create_engine(test_url)
        try:
            with migration_engine.begin() as connection:
                config = Config(str(BACKEND_ROOT / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            yield test_url
        finally:
            migration_engine.dispose()
            with admin_engine.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')
    finally:
        admin_engine.dispose()


@pytest.fixture(autouse=True)
def database_environment(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDEA_BOARD_DATABASE_URL", database_url)


@pytest.fixture
def database_engine(database_environment: None) -> Iterator[Engine]:
    engine = create_database_engine()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def clear_test_database(database_engine: Engine) -> None:
    with database_engine.begin() as connection:
        connection.exec_driver_sql("TRUNCATE TABLE ideas RESTART IDENTITY")


@pytest.fixture
def migration_config(database_engine: Engine) -> Iterator[Config]:
    with database_engine.connect() as connection:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        yield config
