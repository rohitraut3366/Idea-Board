import json
import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from recommendations import recommendation

from config import Target, chart_source, deployment_manifests, manifests
from deploy import release
from rollback import checkpoint, record_healthy, rollback, state
from root import shared_root

OLD = "a" * 40
NEW = "b" * 40
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_cloud_plan_updates_bootstrap_root_and_keeps_operator_enabled(cloud, environment):
    target = Target(cloud, environment, NEW, NEW)
    proposal = recommendation(cloud, environment)
    documents = deployment_manifests(target, proposal)
    assert len(documents) == 1
    parent = documents[0]
    assert parent["metadata"]["name"] == "idea-board"
    output = subprocess.check_output(
        [
            "helm",
            "template",
            "root",
            str(ROOT / "gitops/applications"),
            "-n",
            "argocd",
            "-f",
            str(ROOT / f"gitops/applications/values-{cloud}.yaml"),
            "-f",
            "-",
        ],
        input=json.dumps(parent["spec"]["source"]["helm"]["valuesObject"]),
        text=True,
    )
    assert output.count("kind: Application") == 3
    assert "name: external-secrets\n" in output
    for service in ("backend", "frontend"):
        child = next(
            doc for doc in output.split("---") if f"name: {target.namespace}-{service}\n" in doc
        )
        assert f"namespace: {target.namespace}" in child
        assert "project: idea-board" in child
        assert NEW in child
        assert f"tag: {NEW}" in child
        assert f"- values-{cloud}.yaml" in child


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
@pytest.mark.parametrize("backend_fails", [False, True])
def test_cloud_release_updates_only_owning_root_and_preserves_frontend(
    cloud, backend_fails, monkeypatch, tmp_path
):
    target = Target(cloud, "staging", NEW, NEW)
    previous = manifests(Target(cloud, "staging", OLD, OLD), recommendation(cloud))[1:]
    current = shared_root(target, previous)
    current["spec"]["source"]["helm"]["valuesObject"]["applications"]["external-secrets"] = {
        "source": {"helm": {"valuesObject": {"custom": "preserve"}}}
    }
    cluster = Mock(namespace=target.namespace)
    cluster.public_url.return_value = "https://app.example.com"
    cluster.get.side_effect = lambda kind, name, *args: (
        deepcopy(current) if name == "idea-board" else None
    )
    if backend_fails:

        def wait(applications):
            if applications[0]["metadata"]["name"].endswith("-backend"):
                raise TimeoutError("backend failed")

        cluster.wait.side_effect = wait
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("diagnosis.collect", lambda *args: {})
    if backend_fails:
        with pytest.raises(TimeoutError):
            release(cluster, target, recommendation(cloud))
    else:
        release(cluster, target, recommendation(cloud))
    cluster.database_url.assert_not_called()
    parents = [
        entry.args[0]
        for entry in cluster.apply.call_args_list
        if entry.args[0]["kind"] == "Application"
    ]
    assert len(parents) == (1 if backend_fails else 2)
    assert all(parent["metadata"]["name"] == "idea-board" for parent in parents)
    first = parents[0]["spec"]["source"]["helm"]["valuesObject"]["applications"]
    assert first["frontend"]["source"] == previous[1]["spec"]["source"]
    assert chart_source({"spec": first["backend"]})["helm"]["valuesObject"]["image"]["tag"] == NEW
    assert (
        first["external-secrets"]
        == current["spec"]["source"]["helm"]["valuesObject"]["applications"]["external-secrets"]
    )
    if not backend_fails:
        final = parents[1]["spec"]["source"]["helm"]["valuesObject"]["applications"]
        assert final["frontend"]["source"]["helm"]["valuesObject"]["image"]["tag"] == NEW
        events = cluster.method_calls
        backend_wait = next(
            i
            for i, call in enumerate(events)
            if call[0] == "wait" and call.args[0][0]["metadata"]["name"].endswith("-backend")
        )
        frontend_update = next(
            i for i, call in enumerate(events) if call[0] == "apply" and call.args[0] == parents[1]
        )
        assert backend_wait < frontend_update


@pytest.mark.parametrize(
    "field,value", [("cloud", "gcp"), ("clusterName", "idea-board-production")]
)
def test_wrong_cloud_or_environment_is_rejected_before_mutation(
    field, value, monkeypatch, tmp_path
):
    target = Target("aws", "staging", NEW, NEW)
    current = shared_root(target, [])
    current["spec"]["source"]["helm"]["valuesObject"][field] = value
    cluster = Mock(namespace=target.namespace)
    cluster.get.return_value = current
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        release(cluster, target, recommendation("aws"))
    cluster.apply.assert_not_called()
    cluster.database_url.assert_not_called()


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
@pytest.mark.parametrize("failure", [None, "drift", "running"])
def test_cloud_rollback_keeps_root_active_and_restores_owned_sources(cloud, failure):
    target = Target(cloud, "staging", NEW, NEW)
    old = manifests(Target(cloud, "staging", OLD, OLD), recommendation(cloud))[1:]
    new = manifests(target, recommendation(cloud))[1:]
    cluster = Mock(namespace=target.namespace)
    documents = {}

    def apply(document, force=False):
        documents[(document["kind"].lower(), document["metadata"]["name"])] = deepcopy(document)

    cluster.apply.side_effect = apply
    cluster.get.side_effect = lambda kind, name, *args: deepcopy(documents.get((kind, name)))
    for child in new:
        apply(child)
    parent = shared_root(target, new)
    if failure == "drift":
        parent["spec"]["source"]["helm"]["valuesObject"]["applications"]["frontend"]["source"][
            "targetRevision"
        ] = "c" * 40
    if failure == "running":
        parent["status"] = {"operationState": {"phase": "Running"}}
    apply(parent)
    record_healthy(cluster, old)
    checkpoint(cluster, target, new)
    cluster.apply.reset_mock()
    if failure:
        with pytest.raises(ValueError, match="shared root"):
            rollback(cluster, target, True)
        cluster.apply.assert_not_called()
        return
    result = rollback(cluster, target, True)
    assert result["status"] == "rolled_back"
    mutations = [entry.args[0] for entry in cluster.apply.call_args_list]
    assert mutations[0]["metadata"]["name"] == "idea-board"
    assert mutations[0]["spec"]["syncPolicy"]["automated"]["enabled"] is True
    restored = cluster.get("application", "idea-board")
    assert restored["spec"]["syncPolicy"]["automated"]["enabled"] is True
    for service in ("backend", "frontend"):
        source = chart_source(
            {"spec": restored["spec"]["source"]["helm"]["valuesObject"]["applications"][service]}
        )
        assert source["targetRevision"] == OLD
        assert source["helm"]["valuesObject"]["image"]["tag"] == OLD
    backend = cluster.get("application", f"{target.namespace}-backend")
    assert backend["operation"]["sync"]["revisions"] == [OLD, "master"]
    assert "hook" not in backend["operation"]["sync"]["syncStrategy"]
    assert state(cluster)["attempt"] is None
