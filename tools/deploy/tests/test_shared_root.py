import json
import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from recommendations import recommendation

from config import Target, chart_source, manifests
from deploy import cleanup, release
from root import application_key, shared_root

SHA = "a" * 40
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("cloud", ["kind", "aws", "gcp"])
def test_shared_root_keeps_staging_and_multiple_previews_separate(cloud):
    staging = Target(cloud, "staging", SHA, SHA)
    root = shared_root(staging, manifests(staging, recommendation(cloud))[1:])
    targets = [staging]
    for pr in (35, 42):
        target = Target(cloud, "preview", SHA, SHA, pr)
        root = shared_root(target, manifests(target, recommendation(cloud, "preview"))[1:], root)
        targets.append(target)
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
        input=json.dumps(root["spec"]["source"]["helm"]["valuesObject"]),
        text=True,
    )
    rendered = output.split("---")
    for target in targets:
        for child in manifests(target, recommendation(cloud, target.environment))[1:]:
            actual = next(doc for doc in rendered if f"name: {child['metadata']['name']}\n" in doc)
            assert f"namespace: {target.namespace}" in actual
            assert f"project: {child['spec']['project']}" in actual
            assert f"tag: {SHA}" in actual
            assert chart_source(child)["path"] in actual
    assert (
        "name: external-secrets\n" in output
        if cloud != "kind"
        else "name: ingress-controller\n" in output
    )
    assert "path: gitops/applications" not in output


def test_release_preserves_other_environments_and_serving_frontend(monkeypatch, tmp_path):
    target = Target("kind", "staging", SHA, SHA)
    previous = manifests(target, recommendation())[1:]
    previous[1]["spec"]["source"]["helm"]["valuesObject"]["image"]["tag"] = "b" * 40
    root = shared_root(target, previous)
    preview = Target("kind", "preview", SHA, SHA, 35)
    root = shared_root(preview, manifests(preview, recommendation())[1:], root)
    cluster = Mock(namespace=target.namespace)

    def apply(document, **kwargs):
        nonlocal root
        if document["kind"] == "Application":
            root = deepcopy(document)

    cluster.apply.side_effect = apply
    cluster.get.side_effect = lambda kind, name, *args: (
        deepcopy(root) if name == "idea-board" else None
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("diagnosis.collect", lambda *args: {})
    release(cluster, target, recommendation())
    roots = [
        call.args[0]
        for call in cluster.apply.call_args_list
        if call.args[0]["kind"] == "Application"
    ]
    assert len(roots) == 2
    first = roots[0]["spec"]["source"]["helm"]["valuesObject"]["applications"]
    final = roots[1]["spec"]["source"]["helm"]["valuesObject"]["applications"]
    assert first["idea-board-staging-frontend"]["source"] == previous[1]["spec"]["source"]
    assert (
        final["idea-board-staging-frontend"]["source"]["helm"]["valuesObject"]["image"]["tag"]
        == SHA
    )
    assert first["idea-board-pr-35-backend"] == final["idea-board-pr-35-backend"]
    events = cluster.method_calls
    backend_wait = next(
        i
        for i, call in enumerate(events)
        if call[0] == "wait" and call.args[0][0]["metadata"]["name"].endswith("-backend")
    )
    final_apply = next(
        i for i, call in enumerate(events) if call[0] == "apply" and call.args[0] == roots[1]
    )
    assert backend_wait < final_apply


@pytest.mark.parametrize("cloud", ["kind", "aws", "gcp"])
def test_cleanup_removes_only_requested_preview_from_shared_root(cloud):
    staging = Target(cloud, "staging", SHA, SHA)
    root = shared_root(staging, manifests(staging, recommendation(cloud))[1:])
    previews = [Target(cloud, "preview", SHA, SHA, pr) for pr in (35, 42)]
    for target in previews:
        root = shared_root(target, manifests(target, recommendation(cloud, "preview"))[1:], root)
    cluster = Mock(namespace=previews[0].namespace)
    cluster.get.side_effect = lambda kind, name, *args: (
        deepcopy(root) if name == "idea-board" else None
    )
    cleanup(cluster, previews[0])
    updated = cluster.apply.call_args.args[0]
    entries = updated["spec"]["source"]["helm"]["valuesObject"]["applications"]
    for service in ("backend", "frontend"):
        assert application_key(previews[0], service) not in entries
        assert application_key(previews[1], service) in entries
        assert application_key(staging, service) in entries
    calls = [call.args for call in cluster.run.call_args_list]
    assert all("idea-board" not in call for call in calls)
    assert calls[0][4] == "idea-board-pr-35-frontend"


@pytest.mark.parametrize("invalid", [None, "project", "running", "child"])
def test_existing_parent_is_orphaned_only_after_ownership_checks(invalid):
    from config import REPOSITORY
    from root import environment_root

    target = Target("kind", "staging", SHA, SHA)
    children = manifests(target, recommendation())[1:]
    root = shared_root(target, [])
    parent = {
        "spec": {
            "project": target.namespace,
            "source": {
                "repoURL": REPOSITORY,
                "path": "gitops/applications",
                "helm": {
                    "valuesObject": {
                        "namespace": target.namespace,
                        "namePrefix": target.namespace + "-",
                    }
                },
            },
        },
    }
    if invalid == "project":
        parent["spec"]["project"] = "unrelated"
    elif invalid == "running":
        parent["operation"] = {"sync": {}}
    elif invalid == "child":
        children[1]["spec"]["destination"]["namespace"] = "unrelated"
    documents = {
        "idea-board": root,
        target.namespace: parent,
        **{child["metadata"]["name"]: child for child in children},
    }
    cluster = Mock()
    cluster.get.side_effect = lambda kind, name, *args: deepcopy(documents.get(name))
    if invalid:
        with pytest.raises(ValueError):
            environment_root(cluster, target)
        cluster.run.assert_not_called()
        return
    adopted = environment_root(cluster, target)
    entries = adopted["spec"]["source"]["helm"]["valuesObject"]["applications"]
    for child in children:
        assert entries[child["metadata"]["name"]]["source"] == child["spec"]["source"]
    patch, delete = [call.args for call in cluster.run.call_args_list]
    assert json.loads(patch[-1])["metadata"]["finalizers"] == []
    assert delete[2:5] == ("delete", "application", target.namespace)
    assert "--cascade=orphan" in delete
    assert all("namespace" not in call[2:4] for call in (patch, delete))


def test_root_updates_include_resource_version_without_changing_other_entries():
    target = Target("kind", "preview", SHA, SHA, 35)
    root = shared_root(target, [])
    root["metadata"]["resourceVersion"] = "17"
    root["spec"]["source"]["helm"]["valuesObject"]["applications"] = {
        "ingress-controller": {"enabled": True},
    }
    updated = shared_root(target, manifests(target, recommendation())[1:], root)
    assert updated["metadata"]["resourceVersion"] == "17"
    assert updated["spec"]["source"]["helm"]["valuesObject"]["applications"][
        "ingress-controller"
    ] == {"enabled": True}
