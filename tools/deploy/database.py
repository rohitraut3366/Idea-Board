"""Create stable credentials for an environment's bundled PostgreSQL instance."""

import base64
import secrets
from urllib.parse import unquote, urlsplit


def ensure_database_secret(cluster):
    postgres_host = f"postgres.{cluster.namespace}.svc.cluster.local"
    existing_database_secret = cluster.get_resource(
        "secret", "idea-board-database", cluster.namespace
    )
    if existing_database_secret:
        secret_data = existing_database_secret["data"]
        parsed_database_url = urlsplit(base64.b64decode(secret_data["DATABASE_URL"]).decode())
        database_password = base64.b64decode(secret_data.get("POSTGRES_PASSWORD", "")).decode()
        if (
            parsed_database_url.hostname != postgres_host
            or parsed_database_url.path != "/idea_board"
            or parsed_database_url.username != "idea_board"
            or not database_password
            or unquote(parsed_database_url.password or "") != database_password
        ):
            raise ValueError(
                "existing database Secret does not match this environment's PostgreSQL; "
                "migrate its data or recreate the environment before deploying"
            )
        return
    database_password = secrets.token_urlsafe(32)
    cluster.apply_resource(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "idea-board-database", "namespace": cluster.namespace},
            "type": "Opaque",
            "stringData": {
                "POSTGRES_PASSWORD": database_password,
                "DATABASE_URL": (
                    f"postgresql+psycopg://idea_board:{database_password}@{postgres_host}:5432/idea_board"
                ),
            },
        }
    )
