from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_database_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    monkeypatch.setattr("idea_board.server.create_database_engine", lambda settings: engine)
