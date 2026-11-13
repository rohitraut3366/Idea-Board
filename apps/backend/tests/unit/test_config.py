import pytest
from pydantic import SecretStr, ValidationError

from idea_board.config import Settings


def test_configuration_requires_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IDEA_BOARD_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_postgresql_url_preserves_credentials_and_tls_options() -> None:
    database_url = "postgresql://test:p%40ssword@db.example.test/ideas?sslmode=verify-full"
    settings = Settings(_env_file=None, database_url=SecretStr(database_url))
    assert settings.database_url.get_secret_value() == database_url.replace(
        "postgresql://", "postgresql+psycopg://"
    )
    assert "p%40ssword" not in repr(settings)


@pytest.mark.parametrize(
    "database_url",
    [
        "not-a-url",
        "sqlite:///ideas.db",
        "postgresql://localhost/ideas",
        "postgresql://test:secret@localhost",
        "postgresql://test:secret@localhost:70000/ideas",
    ],
)
def test_invalid_database_configuration_hides_input(database_url: str) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=SecretStr(database_url))
    assert database_url not in str(error.value)


def test_nonpositive_database_settings_fail_startup() -> None:
    with pytest.raises(ValidationError, match="database_pool_size"):
        Settings(
            _env_file=None,
            database_url=SecretStr("postgresql://test:secret@localhost/ideas"),
            database_pool_size=0,
        )
