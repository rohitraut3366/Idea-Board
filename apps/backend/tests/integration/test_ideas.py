from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, select
from sqlalchemy.exc import IntegrityError

from idea_board.models import Idea
from idea_board.server import create_app


def test_empty_database_is_healthy(client: TestClient) -> None:
    assert client.get("/api/ideas").json() == []
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_returns_committed_trimmed_content_and_utc_time(
    client: TestClient, database_engine: Engine
) -> None:
    response = client.post("/api/ideas", json={"content": "  A better build pipeline \n"})
    assert response.status_code == 201
    idea = response.json()
    assert idea["id"] == "1"
    assert idea["content"] == "A better build pipeline"
    assert datetime.fromisoformat(idea["created_at"]).utcoffset() == timedelta(0)
    with database_engine.connect() as connection:
        assert connection.scalar(select(Idea.content)) == idea["content"]
    assert client.get("/api/ideas").json() == [idea]


@pytest.mark.parametrize(
    "content", ["🚀" * 2000, "  " + "x" * 2000 + "  ", "'; DROP TABLE ideas; --"]
)
def test_valid_content_boundaries_and_sql_metacharacters(client: TestClient, content: str) -> None:
    response = client.post("/api/ideas", json={"content": content})
    assert response.status_code == 201
    assert response.json()["content"] == content.strip()
    assert client.get("/api/ideas").json() == [response.json()]


def test_full_list_and_keyset_pages_remain_consistent_during_new_writes(client: TestClient) -> None:
    for number in range(5):
        assert client.post("/api/ideas", json={"content": f"Idea {number}"}).status_code == 201

    first_page = client.get("/api/ideas?limit=2")
    assert [idea["id"] for idea in first_page.json()] == ["5", "4"]
    next_url = first_page.headers["Link"].split("<", 1)[1].split(">", 1)[0]

    assert client.post("/api/ideas", json={"content": "Newer idea"}).status_code == 201
    second_page = client.get(next_url)
    assert [idea["id"] for idea in second_page.json()] == ["3", "2"]
    last_page = client.get("/api/ideas?limit=2&before_id=2")
    assert [idea["id"] for idea in last_page.json()] == ["1"]
    assert "Link" not in last_page.headers

    all_ideas = client.get("/api/ideas")
    assert [idea["id"] for idea in all_ideas.json()] == ["6", "5", "4", "3", "2", "1"]
    assert "Link" not in all_ideas.headers


def test_bigint_ids_are_not_rounded(client: TestClient, database_engine: Engine) -> None:
    large_id = 2**53 + 1
    with database_engine.begin() as connection:
        connection.execute(insert(Idea).values(id=large_id, content="Large identifier"))
    response = client.get(f"/api/ideas?limit=1&before_id={large_id + 1}")
    assert response.json()[0]["id"] == str(large_id)


def test_concurrent_acknowledged_writes_are_present_once(
    client: TestClient, database_engine: Engine
) -> None:
    contents = [f"Concurrent idea {number}" for number in range(20)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(
            executor.map(
                lambda content: client.post("/api/ideas", json={"content": content}), contents
            )
        )
    assert all(response.status_code == 201 for response in responses)
    assert len({response.json()["id"] for response in responses}) == 20
    assert {idea["content"] for idea in client.get("/api/ideas").json()} == set(contents)
    with database_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Idea)) == 20


def test_data_survives_a_new_application_instance() -> None:
    with TestClient(create_app()) as first_client:
        response = first_client.post("/api/ideas", json={"content": "Keep this after restart"})
        assert response.status_code == 201
    with TestClient(create_app()) as second_client:
        assert second_client.get("/api/ideas").json() == [response.json()]


@pytest.mark.parametrize("content", ["", "x" * 2001])
def test_database_also_enforces_content_length(database_engine: Engine, content: str) -> None:
    with pytest.raises(IntegrityError), database_engine.begin() as connection:
        connection.execute(insert(Idea).values(content=content))


def test_duplicate_content_is_rejected_after_trimming(client: TestClient) -> None:
    first = client.post("/api/ideas", json={"content": "Same idea"})
    assert first.status_code == 201
    duplicate = client.post("/api/ideas", json={"content": "  Same idea\n"})
    assert duplicate.status_code == 409
    assert client.get("/api/ideas").json() == [first.json()]
    assert client.post("/api/ideas", json={"content": "same idea"}).status_code == 201


def test_concurrent_duplicate_submissions_create_one_idea(client: TestClient) -> None:
    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(
            executor.map(
                lambda _: client.post("/api/ideas", json={"content": "One shared idea"}), range(8)
            )
        )
    assert sorted(response.status_code for response in responses) == [201] + [409] * 7
    assert len(client.get("/api/ideas").json()) == 1


def test_database_rejects_duplicate_long_unicode_text(
    client: TestClient, database_engine: Engine
) -> None:
    content = "".join(chr(0x10000 + index) for index in range(2000))
    assert client.post("/api/ideas", json={"content": content}).status_code == 201
    with pytest.raises(IntegrityError), database_engine.begin() as connection:
        connection.execute(insert(Idea).values(content=content))
    assert client.post("/api/ideas", json={"content": content + " "}).status_code == 409


def test_delete_removes_only_the_selected_idea_and_allows_resubmission(client: TestClient) -> None:
    first = client.post("/api/ideas", json={"content": "Delete this"}).json()
    second = client.post("/api/ideas", json={"content": "Keep this"}).json()
    response = client.delete(f"/api/ideas/{first['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/api/ideas").json() == [second]
    assert client.delete(f"/api/ideas/{first['id']}").status_code == 404
    assert client.post("/api/ideas", json={"content": "Delete this"}).status_code == 201


@pytest.mark.parametrize("idea_id", ["0", "-1", str(2**63), "abc"])
def test_delete_rejects_invalid_ids(client: TestClient, idea_id: str) -> None:
    assert client.delete(f"/api/ideas/{idea_id}").status_code == 422


def test_delete_supports_large_ids(client: TestClient, database_engine: Engine) -> None:
    large_id = 2**53 + 1
    with database_engine.begin() as connection:
        connection.execute(insert(Idea).values(id=large_id, content="Delete a large identifier"))
    assert client.delete(f"/api/ideas/{large_id}").status_code == 204
    assert client.get("/api/ideas").json() == []
