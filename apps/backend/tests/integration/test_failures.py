import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from idea_board.server import create_app


def test_unavailable_database_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://idea_board:private-password@127.0.0.1:1/unavailable",
    )
    with pytest.raises(RuntimeError) as error:
        with TestClient(create_app()):
            pytest.fail("Startup should fail before serving requests")
    assert "private-password" not in str(error.value)


def test_database_failure_after_startup_returns_safe_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
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
            assert "private-password" not in response.text
            assert "Do not log my idea" not in response.text
