import pytest

from idea_board.database import create_database_engine


def test_missing_database_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(KeyError, match="DATABASE_URL"):
        create_database_engine()
