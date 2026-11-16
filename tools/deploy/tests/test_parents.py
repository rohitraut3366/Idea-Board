import json
import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from recommendations import recommendation

from config import Target, deployment_manifests, manifests
from deploy import cleanup, release

SHA = "a" * 40
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("environment", ["staging", "preview", "production"])
def test_parent_chart_preserves_child_sources_and_environment_boundaries(environment):
    target = Target("kind", environment, SHA, SHA, 42 if environment == "preview" else None)
    project, *children = manifests(target, recommendation(environment=environment))
    rendered = deployment_manifests(target, recommendation(environment=environment))
    parent = rendered[1]
    assert len(rendered) == 2
    assert parent["metadata"]["name"] == target.namespace
    assert parent["spec"]["destination"]["namespace"] == "argocd"
    assert {"server": "https://kubernetes.default.svc", "namespace": "argocd"} in project["spec"][
        "destinations"
    ]
    output = subprocess.run(
        [
            "helm",
            "template",
            "environment",
            str(ROOT / "gitops/applications"),
            "-n",
            "argocd",
            "-f",
            "-",
        ],
        input=json.dumps(parent["spec"]["source"]["helm"]["valuesObject"]),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for child in children:
        assert f"name: {child['metadata']['name']}" in output
        assert f"namespace: {target.namespace}" in output
        assert child["spec"]["source"]["path"] in output
    assert f"host: {target.namespace}.localhost" in output
    assert output.count("kind: Application") == 2
    assert "kind: Secret" not in output


def test_release_preserves_serving_frontend_until_backend_is_verified(monkeypatch, tmp_path):
    target = Target("kind", "staging", SHA, SHA)
    previous = manifests(target, recommendation())[2]
    previous["spec"]["source"]["helm"]["valuesObject"]["image"]["tag"] = "b" * 40
    cluster = Mock(namespace=target.namespace)
    cluster.get.side_effect = lambda kind, name, *args: (
        deepcopy(previous) if name.endswith("-frontend") else None
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("diagnosis.collect", lambda *args: {})
    release(cluster, target, recommendation())
    parents = [
        entry.args[0]
        for entry in cluster.apply.call_args_list
        if entry.args[0]["kind"] == "Application"
    ]
    assert len(parents) == 2
    assert all(app["metadata"]["name"] == target.namespace for app in parents)
    first = parents[0]["spec"]["source"]["helm"]["valuesObject"]["applications"]
    final = parents[1]["spec"]["source"]["helm"]["valuesObject"]["applications"]
    assert first["frontend"]["source"] == previous["spec"]["source"]
    assert final["frontend"]["source"]["helm"]["valuesObject"]["image"]["tag"] == SHA
    events = cluster.method_calls
    backend_wait = next(
        i
        for i, entry in enumerate(events)
        if entry[0] == "wait" and entry.args[0][0]["metadata"]["name"].endswith("-backend")
    )
    final_apply = next(
        i for i, entry in enumerate(events) if entry[0] == "apply" and entry.args[0] == parents[1]
    )
    assert backend_wait < final_apply


def test_preview_cleanup_deletes_parent_before_children(monkeypatch):
    cluster = Mock(namespace="idea-board-pr-42")
    cluster.get.return_value = None
    cleanup(cluster, Target("kind", "preview", SHA, SHA, 42))
    calls = [entry.args for entry in cluster.run.call_args_list]
    assert calls[0][3:5] == ("application", "idea-board-pr-42")
    assert calls[1][4] == "idea-board-pr-42-frontend"
