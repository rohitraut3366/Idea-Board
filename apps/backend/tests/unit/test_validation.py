import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"content": ""},
        {"content": " \t\n "},
        {"content": "x" * 2001},
        {"content": None},
        {"content": 42},
        {"content": True},
        {"content": "idea", "id": "1"},
        {"content": "bad\x00text"},
    ],
)
def test_invalid_ideas_are_rejected_before_database_access(
    client: TestClient, payload: dict[str, object]
) -> None:
    response = client.post("/api/ideas", json=payload)
    assert response.status_code == 422
    assert all("input" not in error for error in response.json()["detail"])


@pytest.mark.parametrize("body", [b'{"content":', b'{"content":"\\ud800"}'])
def test_invalid_json_or_unicode_returns_a_safe_validation_error(
    client: TestClient, body: bytes
) -> None:
    response = client.post("/api/ideas", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=abc",
        "before_id=1",
        "limit=1&before_id=0",
        "limit=1&before_id=-1",
        f"limit=1&before_id={2**63}",
    ],
)
def test_invalid_pagination_is_rejected_before_database_access(
    client: TestClient, query: str
) -> None:
    assert client.get(f"/api/ideas?{query}").status_code == 422


def test_only_one_health_endpoint_is_exposed(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {path for path in paths if path.startswith("/health")} == {"/health"}


def test_openapi_describes_ids_as_strings(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["components"]["schemas"]["IdeaResponse"]["properties"]["id"]["type"] == "string"
