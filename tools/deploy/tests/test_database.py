import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from database import (
    delete_preview,
    driver_url,
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
