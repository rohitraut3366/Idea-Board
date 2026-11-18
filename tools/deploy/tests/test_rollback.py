from copy import deepcopy
from unittest.mock import Mock

import pytest
from recommendations import recommendation

from config import (
    Target,
    build_environment_parent_application,
    build_project_and_service_applications,
)
from rollback import read_release_state, record_healthy_release, record_release_attempt, rollback

OLD = "a" * 40
NEW = "b" * 40


@pytest.fixture
def cluster():
    client = Mock(namespace="idea-board-staging")
    resource_store = {}

    def apply(resource_manifest, force=False):
        resource_store[
            (resource_manifest["kind"].lower(), resource_manifest["metadata"]["name"])
        ] = deepcopy(resource_manifest)

    def get(kind, name, namespace=None):
        return deepcopy(resource_store.get((kind, name)))

    client.apply_resource.side_effect = apply
    client.get_resource.side_effect = get
    client.resource_store = resource_store
    old = build_project_and_service_applications(
        Target("kind", "staging", OLD, OLD), recommendation()
    )[1:]
    new = build_project_and_service_applications(
        Target("kind", "staging", NEW, NEW), recommendation()
    )[1:]
    for application in new:
        apply(application)
    apply(build_environment_parent_application(Target("kind", "staging", NEW, NEW), new))
    record_healthy_release(client, old)
    record_release_attempt(client, Target("kind", "staging", NEW, NEW), new)
    client.apply_resource.reset_mock()
    return client


def test_rollback_restores_both_argo_sources_and_skips_migration_hooks(cluster):
    result = rollback(cluster, Target("kind", "staging", NEW, NEW), True)
    assert result["status"] == "rolled_back"
    for service in ("backend", "frontend"):
        restored = cluster.get_resource("application", f"idea-board-staging-{service}")
        assert restored["spec"]["source"]["targetRevision"] == OLD
        assert restored["spec"]["source"]["helm"]["valuesObject"]["image"]["tag"] == OLD
        assert restored["spec"]["syncPolicy"]["automated"]["enabled"] is False
        assert restored["operation"]["sync"] == {
            "revision": OLD,
            "syncStrategy": {"apply": {}},
        }
        assert restored["operation"]["info"][0]["name"] == "idea-board/rollback-id"
    cluster.verify_application_http.assert_called_once()
    assert read_release_state(cluster)["attempt"] is None
    assert all(
        "operation" not in application for application in read_release_state(cluster)["healthy"]
    )


@pytest.mark.parametrize(
    "failure",
    [
        "schema",
        "sha",
        "drift",
        "running",
        "pending",
        "no_previous",
        "parent_drift",
        "parent_running",
    ],
)
def test_rollback_guards_run_before_any_application_mutation(cluster, failure):
    target = Target("kind", "staging", NEW, NEW)
    if failure == "sha":
        target = Target("kind", "staging", "c" * 40, NEW)
    elif failure in {"drift", "running", "pending"}:
        # Frontend guard failure must also prevent a partial backend rollback.
        application = cluster.resource_store[("application", "idea-board-staging-frontend")]
        if failure == "drift":
            application["spec"]["source"]["targetRevision"] = "c" * 40
        elif failure == "running":
            application["status"] = {"operationState": {"phase": "Running"}}
        else:
            application["operation"] = {"sync": {"syncStrategy": {"hook": {}}}}
    elif failure == "parent_drift":
        cluster.resource_store[("application", "idea-board-staging")]["spec"]["source"][
            "targetRevision"
        ] = "c" * 40
    elif failure == "parent_running":
        cluster.resource_store[("application", "idea-board-staging")]["status"] = {
            "operationState": {"phase": "Running"}
        }
    elif failure == "no_previous":
        record_healthy_release(cluster, None)
        cluster.apply_resource.reset_mock()
    with pytest.raises(ValueError):
        rollback(cluster, target, failure != "schema")
    cluster.apply_resource.assert_not_called()
    cluster.verify_application_http.assert_not_called()


def test_unverified_rollback_does_not_replace_the_healthy_checkpoint(cluster):
    previous = read_release_state(cluster)["healthy"]
    cluster.verify_application_http.side_effect = RuntimeError("HTTP failed")
    with pytest.raises(RuntimeError):
        rollback(cluster, Target("kind", "staging", NEW, NEW), True)
    assert read_release_state(cluster)["healthy"] == previous
    assert read_release_state(cluster)["attempt"] is not None


def test_rollback_leaves_parent_consistent_and_paused(cluster):
    rollback(cluster, Target("kind", "staging", NEW, NEW), True)
    parent = cluster.get_resource("application", "idea-board-staging")
    assert parent["spec"]["syncPolicy"]["automated"]["enabled"] is False
    values = parent["spec"]["source"]["helm"]["valuesObject"]
    for service in ("backend", "frontend"):
        child = values["applications"][service]
        assert child["source"]["targetRevision"] == OLD
        assert child["syncPolicy"]["automated"]["enabled"] is False
        assert "operation" not in child
    mutations = [entry.args[0] for entry in cluster.apply_resource.call_args_list]
    assert mutations[0]["metadata"]["name"] == "idea-board-staging"
    assert mutations[0]["spec"]["syncPolicy"]["automated"]["enabled"] is False
