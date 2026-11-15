import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from database import (
    delete_preview,
    driver_url,
    managed_database_url,
    prepare_preview,
    preview_names,
)

ADMIN_URL = os.environ.get(
    "IDEA_BOARD_TEST_DATABASE_URL",
    "postgresql+psycopg://idea_board:idea_board_local@127.0.0.1:55432/idea_board",
)


@pytest.fixture
def preview():
    pr = uuid4().int % 800000000 + 100000000
    database, username, _ = preview_names(pr)
    yield pr
    with psycopg.connect(driver_url(ADMIN_URL), autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
        )
        connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(username)))


def test_preview_database_survives_redeploy_and_is_deleted_on_cleanup(preview):
    url = prepare_preview(ADMIN_URL, preview)
    with psycopg.connect(driver_url(url), autocommit=True) as connection:
        connection.execute("CREATE TABLE saved_ideas (content text)")
        connection.execute("INSERT INTO saved_ideas VALUES ('keep across redeploy')")
        assert connection.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        ).fetchone() == (False,)
    assert prepare_preview(ADMIN_URL, preview, url) == url
    with psycopg.connect(driver_url(url)) as connection:
        assert connection.execute("SELECT content FROM saved_ideas").fetchone() == (
            "keep across redeploy",
        )
    delete_preview(ADMIN_URL, preview)
    delete_preview(ADMIN_URL, preview)  # Cleanup can be retried.
    with psycopg.connect(driver_url(ADMIN_URL)) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (preview_names(preview)[0],)
            ).fetchone()
            is None
        )


def test_unrelated_database_is_not_reused_or_deleted(preview):
    database, _, _ = preview_names(preview)
    with psycopg.connect(driver_url(ADMIN_URL), autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    with pytest.raises(ValueError, match="unrelated database"):
        prepare_preview(ADMIN_URL, preview)
    with psycopg.connect(driver_url(ADMIN_URL)) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (preview_names(preview)[1],)
            ).fetchone()
            is None
        )
    with pytest.raises(ValueError, match="unrelated database"):
        delete_preview(ADMIN_URL, preview)
    with psycopg.connect(driver_url(ADMIN_URL)) as connection:
        assert connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
        ).fetchone()


def test_one_preview_cannot_reuse_another_previews_secret(preview):
    url = prepare_preview(ADMIN_URL, preview)
    with pytest.raises(ValueError, match="does not match"):
        prepare_preview(ADMIN_URL, preview + 1, url)


def test_kind_uses_environment_url_without_cloud_secret_configuration(monkeypatch):
    monkeypatch.delenv("DATABASE_CREDENTIAL_SECRET_ID", raising=False)
    monkeypatch.setenv("IDEA_BOARD_DATABASE_URL", ADMIN_URL)
    assert managed_database_url("kind") == ADMIN_URL


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_managed_credentials_are_encoded_without_changing_the_password(monkeypatch, cloud):
    import json
    from urllib.parse import unquote, urlsplit

    password = " secret@with:/?# and spaces "
    monkeypatch.setenv("DATABASE_CREDENTIAL_SECRET_ID", "example-secret")
    monkeypatch.setenv("DATABASE_HOST", "private.example.test")
    monkeypatch.setenv("DATABASE_NAME", "idea_board")
    monkeypatch.setenv("DATABASE_USERNAME", "app_user")
    monkeypatch.setenv("DATABASE_PORT", "5432")
    response = (
        json.dumps({"SecretString": json.dumps({"username": "app_user", "password": password})})
        if cloud == "aws"
        else password
    )
    monkeypatch.setattr("database.read_command", lambda *args: response)
    parsed = urlsplit(managed_database_url(cloud))
    assert unquote(parsed.password) == password
    assert parsed.hostname == "private.example.test"
    assert parsed.query == "sslmode=require"
