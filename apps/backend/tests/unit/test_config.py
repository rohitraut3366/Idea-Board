from pathlib import Path

import pytest
from pydantic import ValidationError

from idea_board.config import Settings


def test_configuration_requires_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IDEA_BOARD_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_database_url_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql+psycopg://test:secret@localhost/ideas"
    monkeypatch.setenv("IDEA_BOARD_DATABASE_URL", database_url)
    settings = Settings(_env_file=None)
    assert settings.database_url.get_secret_value() == database_url


def test_environment_overrides_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("IDEA_BOARD_DATABASE_URL=postgresql+psycopg://test:local@localhost/local\n")
    monkeypatch.delenv("IDEA_BOARD_DATABASE_URL", raising=False)
    assert Settings(_env_file=dotenv).database_url.get_secret_value().endswith("/local")
    monkeypatch.setenv("IDEA_BOARD_DATABASE_URL", "postgresql+psycopg://test:ci@localhost/ci")
    assert Settings(_env_file=dotenv).database_url.get_secret_value().endswith("/ci")
