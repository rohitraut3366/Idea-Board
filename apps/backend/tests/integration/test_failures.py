from typing import cast

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from idea_board.config import Settings
from idea_board.server import create_app


def test_unavailable_database_fails_startup() -> None:
    settings = Settings(
        _env_file=None,
        database_url=SecretStr("postgresql://idea_board:private-password@127.0.0.1:1/unavailable"),
    )
    with pytest.raises(RuntimeError, match="Database or schema unavailable") as error:
        with TestClient(create_app(settings)):
            pytest.fail("Startup should fail before serving requests")
    assert "private-password" not in str(error.value)


def test_database_failure_after_startup_returns_safe_errors(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(settings)
    with TestClient(app) as client:

        def fail_connection(*args: object, **kwargs: object) -> None:
            raise OperationalError("private query", {}, Exception("private-password"))

        monkeypatch.setattr(app.state.engine, "connect", fail_connection)
        for response in (
            client.get("/health"),
            client.get("/api/ideas"),
            client.post("/api/ideas", json={"content": "Do not log my idea"}),
        ):
            assert response.status_code == 503
            assert response.json() == {"detail": "Database unavailable"}
            assert "private-password" not in response.text
            assert "Do not log my idea" not in response.text


def test_pool_exhaustion_is_bounded_and_recovers(settings: Settings) -> None:
    settings = settings.model_copy(
        update={"database_pool_size": 1, "database_pool_timeout_seconds": 0.1}
    )
    app = create_app(settings)
    with TestClient(app) as client:
        engine = cast(Engine, app.state.engine)
        with engine.connect():
            assert client.get("/health").status_code == 503
        assert client.get("/health").status_code == 200
