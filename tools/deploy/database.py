"""Read managed credentials and isolate preview databases on the staging server."""

import json
import os
import secrets
import subprocess
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import psycopg
from psycopg import sql


def read_command(*arguments):
    return subprocess.check_output(arguments, text=True)


def managed_database_url(cloud):
    if cloud == "kind":
        return os.environ["IDEA_BOARD_DATABASE_URL"]
    secret_id = os.environ["DATABASE_CREDENTIAL_SECRET_ID"]
    if cloud == "aws":
        response = json.loads(
            read_command(
                "aws",
                "secretsmanager",
                "get-secret-value",
                "--secret-id",
                secret_id,
                "--output",
                "json",
                "--no-cli-pager",
            )
        )
        credentials = json.loads(response["SecretString"])
        username, password = credentials["username"], credentials["password"]
    elif cloud == "gcp":
        password = read_command(
            "gcloud", "secrets", "versions", "access", "latest", "--secret", secret_id
        )
        username = os.environ["DATABASE_USERNAME"]
    else:
        raise ValueError("unsupported cloud")
    host = os.environ["DATABASE_HOST"]
    port = int(os.environ.get("DATABASE_PORT", "5432"))
    database = os.environ["DATABASE_NAME"]
    return (
        f"postgresql+psycopg://{quote(username, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}?sslmode=require"
    )


def driver_url(url):
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def preview_names(pr):
    if type(pr) is not int or not 1 <= pr <= 999999999:
        raise ValueError("invalid preview PR number")
    name = f"idea_board_pr_{pr}"
    return name, name, f"idea-board-preview:{pr}"


def prepare_preview(admin_url, pr, existing_url=None):
    database, username, marker = preview_names(pr)
    existing = urlsplit(existing_url) if existing_url else None
    admin = urlsplit(admin_url)
    if existing and (
        unquote(existing.path[1:]) != database
        or unquote(existing.username or "") != username
        or existing.hostname != admin.hostname
        or existing.port != admin.port
    ):
        raise ValueError("existing preview Secret does not match the requested database")
    password = (
        unquote(existing.password) if existing and existing.password else secrets.token_urlsafe(32)
    )
    with psycopg.connect(driver_url(admin_url), autocommit=True) as connection:
        row = connection.execute(
            "SELECT shobj_description(oid, 'pg_database'), pg_get_userbyid(datdba) "
            "FROM pg_database WHERE datname = %s",
            (database,),
        ).fetchone()
        if row and row != (marker, username):
            raise ValueError("refusing to reuse an unrelated database")
        role = connection.execute(
            "SELECT shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname = %s",
            (username,),
        ).fetchone()
        if role and role[0] != marker:
            raise ValueError("refusing to reuse an unrelated database role")
        if not role:
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(username),
                    sql.Literal(password),
                )
            )
            connection.execute(
                sql.SQL("COMMENT ON ROLE {} IS {}").format(
                    sql.Identifier(username),
                    sql.Literal(marker),
                )
            )
        else:
            connection.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(username),
                    sql.Literal(password),
                )
            )
        connection.execute(sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(username)))
        if not row:
            connection.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(database),
                    sql.Identifier(username),
                )
            )
            connection.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(database),
                    sql.Literal(marker),
                )
            )
        connection.execute(
            sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(database),
            )
        )
    authority = (
        f"{quote(username, safe='')}:{quote(password, safe='')}"
        f"@{admin.hostname}:{admin.port or 5432}"
    )
    return urlunsplit((admin.scheme, authority, "/" + database, admin.query, ""))


def delete_preview(admin_url, pr):
    database, username, marker = preview_names(pr)
    with psycopg.connect(driver_url(admin_url), autocommit=True) as connection:
        row = connection.execute(
            "SELECT shobj_description(oid, 'pg_database'), pg_get_userbyid(datdba) "
            "FROM pg_database WHERE datname = %s",
            (database,),
        ).fetchone()
        if row:
            if row != (marker, username):
                raise ValueError("refusing to drop an unrelated database")
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
            )
        role = connection.execute(
            "SELECT shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname = %s",
            (username,),
        ).fetchone()
        if role:
            if role[0] != marker:
                raise ValueError("refusing to drop an unrelated role")
            connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(username)))
