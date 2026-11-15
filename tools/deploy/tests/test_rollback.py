from copy import deepcopy
from unittest.mock import Mock

import pytest
from recommendations import recommendation

from config import Target, manifests
from rollback import checkpoint, record_healthy, rollback, state

OLD = "a" * 40
NEW = "b" * 40


@pytest.fixture
def cluster():
    client = Mock(namespace="idea-board-staging")
    documents = {}

    def apply(document):
        documents[(document["kind"].lower(), document["metadata"]["name"])] = deepcopy(document)

    def get(kind, name, namespace=None):
        return deepcopy(documents.get((kind, name)))

    client.apply.side_effect = apply
    client.get.side_effect = get
    client.documents = documents
    old = manifests(Target("kind", "staging", OLD, OLD), recommendation())[1:]
    new = manifests(Target("kind", "staging", NEW, NEW), recommendation())[1:]
    for app in new:
        apply(app)
    record_healthy(client, old)
    checkpoint(client, Target("kind", "staging", NEW, NEW), new)
    client.apply.reset_mock()
    return client


def test_rollback_restores_both_argo_sources_and_skips_migration_hooks(cluster):
    result = rollback(cluster, Target("kind", "staging", NEW, NEW), True)
    assert result["status"] == "rolled_back"
    for service in ("backend", "frontend"):
        restored = cluster.get("application", f"idea-board-staging-{service}")
        assert restored["spec"]["source"]["targetRevision"] == OLD
        assert restored["spec"]["source"]["helm"]["valuesObject"]["image"]["tag"] == OLD
        assert restored["spec"]["syncPolicy"]["automated"]["enabled"] is False
        assert restored["operation"]["sync"] == {
            "revision": OLD,
            "syncStrategy": {"apply": {}},
        }
        assert restored["operation"]["info"][0]["name"] == "idea-board/rollback-id"
    cluster.verify.assert_called_once()
    assert state(cluster)["attempt"] is None
    assert all("operation" not in app for app in state(cluster)["healthy"])


@pytest.mark.parametrize("failure", ["schema", "sha", "drift", "running", "pending", "no_previous"])
def test_rollback_guards_run_before_any_application_mutation(cluster, failure):
    target = Target("kind", "staging", NEW, NEW)
    if failure == "sha":
        target = Target("kind", "staging", "c" * 40, NEW)
    elif failure in {"drift", "running", "pending"}:
        # Frontend guard failure must also prevent a partial backend rollback.
        app = cluster.documents[("application", "idea-board-staging-frontend")]
        if failure == "drift":
            app["spec"]["source"]["targetRevision"] = "c" * 40
        elif failure == "running":
            app["status"] = {"operationState": {"phase": "Running"}}
        else:
            app["operation"] = {"sync": {"syncStrategy": {"hook": {}}}}
    elif failure == "no_previous":
        record_healthy(cluster, None)
        cluster.apply.reset_mock()
    with pytest.raises(ValueError):
        rollback(cluster, target, failure != "schema")
    cluster.apply.assert_not_called()
    cluster.verify.assert_not_called()


def test_unverified_rollback_does_not_replace_the_healthy_checkpoint(cluster):
    previous = state(cluster)["healthy"]
    cluster.verify.side_effect = RuntimeError("HTTP failed")
    with pytest.raises(RuntimeError):
        rollback(cluster, Target("kind", "staging", NEW, NEW), True)
    assert state(cluster)["healthy"] == previous
    assert state(cluster)["attempt"] is not None
