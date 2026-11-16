"""Create stable credentials for an environment's bundled PostgreSQL instance."""

import base64
import secrets
from urllib.parse import unquote, urlsplit


def ensure_database_secret(cluster):
    host = f"postgres.{cluster.namespace}.svc.cluster.local"
    existing = cluster.get("secret", "idea-board-database", cluster.namespace)
    if existing:
        data = existing["data"]
        url = urlsplit(base64.b64decode(data["DATABASE_URL"]).decode())
        password = base64.b64decode(data.get("POSTGRES_PASSWORD", "")).decode()
        if (
            url.hostname != host
            or url.path != "/idea_board"
            or url.username != "idea_board"
            or not password
            or unquote(url.password or "") != password
        ):
            raise ValueError(
                "existing database Secret does not match this environment's PostgreSQL; "
                "migrate its data or recreate the environment before deploying"
            )
        return
    password = secrets.token_urlsafe(32)
    cluster.apply(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "idea-board-database", "namespace": cluster.namespace},
            "type": "Opaque",
            "stringData": {
                "POSTGRES_PASSWORD": password,
                "DATABASE_URL": (
                    f"postgresql+psycopg://idea_board:{password}@{host}:5432/idea_board"
                ),
            },
        }
    )
