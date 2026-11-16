import base64
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest

from database import ensure_database_secret


def stored_secret(document):
    return {
        "data": {
            key: base64.b64encode(value.encode()).decode()
            for key, value in document["stringData"].items()
        }
    }


def test_environment_credentials_are_local_unique_and_stable_on_redeploy():
    passwords = []
    for namespace in ("idea-board-staging", "idea-board-pr-42", "idea-board-pr-43"):
        cluster = Mock(namespace=namespace)
        cluster.get.return_value = None
        ensure_database_secret(cluster)
        secret = cluster.apply.call_args.args[0]
        url = urlsplit(secret["stringData"]["DATABASE_URL"])
        assert secret["metadata"]["namespace"] == namespace
        assert url.hostname == f"postgres.{namespace}.svc.cluster.local"
        assert url.password == secret["stringData"]["POSTGRES_PASSWORD"]
        passwords.append(url.password)
        cluster.get.return_value = stored_secret(secret)
        cluster.apply.reset_mock()
        ensure_database_secret(cluster)
        cluster.apply.assert_not_called()
        assert all(call.args[2] == namespace for call in cluster.get.call_args_list)
    assert len(set(passwords)) == 3


@pytest.mark.parametrize("host", ["postgres.idea-board.svc.cluster.local", "staging.example.com"])
def test_shared_database_credentials_are_rejected_without_modification(host):
    cluster = Mock(namespace="idea-board-pr-42")
    cluster.get.return_value = stored_secret(
        {
            "stringData": {
                "DATABASE_URL": f"postgresql://idea_board:secret@{host}/idea_board",
                "POSTGRES_PASSWORD": "secret",
            }
        }
    )
    with pytest.raises(ValueError, match="migrate its data or recreate"):
        ensure_database_secret(cluster)
    cluster.apply.assert_not_called()


def test_inconsistent_passwords_are_rejected_without_rotation():
    cluster = Mock(namespace="idea-board-staging")
    cluster.get.return_value = stored_secret(
        {
            "stringData": {
                "DATABASE_URL": (
                    "postgresql://idea_board:old@postgres.idea-board-staging.svc.cluster.local/idea_board"
                ),
                "POSTGRES_PASSWORD": "new",
            }
        }
    )
    with pytest.raises(ValueError, match="existing database Secret"):
        ensure_database_secret(cluster)
    cluster.apply.assert_not_called()
