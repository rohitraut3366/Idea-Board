import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect

from idea_board.server import create_app


def test_migration_is_repeatable_and_matches_models(migration_config: Config) -> None:
    command.upgrade(migration_config, "head")
    command.upgrade(migration_config, "head")
    command.check(migration_config)


def test_empty_schema_is_unhealthy_until_migrated(
    migration_config: Config, database_engine: Engine, client: TestClient
) -> None:
    command.downgrade(migration_config, "base")
    try:
        assert "ideas" not in inspect(database_engine).get_table_names()
        assert client.get("/health").status_code == 503
        with pytest.raises(RuntimeError, match="Database or schema unavailable"):
            with TestClient(create_app()):
                pytest.fail("Startup must fail without the schema")
    finally:
        command.upgrade(migration_config, "head")
    assert "ideas" in inspect(database_engine).get_table_names()
    assert client.get("/health").status_code == 200
    with TestClient(create_app()) as restarted_client:
        assert restarted_client.get("/health").status_code == 200
