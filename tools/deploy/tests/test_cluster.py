from copy import deepcopy
from unittest.mock import MagicMock, Mock, call

import pytest
from recommendations import recommendation

from cluster import Cluster
from config import Target, manifests

SHA = "a" * 40


@pytest.mark.parametrize("address", [{"hostname": "alb.example.com"}, {"ip": "203.0.113.10"}])
def test_public_checks_follow_the_ingress_address_and_check_page_and_api(monkeypatch, address):
    cluster = Cluster("test", "idea-board-pr-42")
    get = Mock(return_value={"status": {"loadBalancer": {"ingress": [address]}}})
    monkeypatch.setattr(cluster, "get", get)
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.read.return_value = "[]"
    request = Mock(return_value=response)
    monkeypatch.setattr("cluster.urlopen", request)
    origin = "http://" + next(iter(address.values()))
    assert cluster.public_url() == origin
    get.assert_called_once_with("ingress", "frontend", "idea-board-pr-42")
    assert request.call_args_list == [
        call(origin, timeout=10),
        call(origin + "/api/ideas?limit=1", timeout=10),
    ]


def test_public_page_without_a_working_api_cannot_pass_release(monkeypatch):
    cluster = Cluster("test", "idea-board-staging")
    monkeypatch.setattr(
        cluster,
        "get",
        Mock(return_value={"status": {"loadBalancer": {"ingress": [{"ip": "203.0.113.10"}]}}}),
    )
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.read.return_value = '{"error": "wrong route"}'
    monkeypatch.setattr("cluster.urlopen", Mock(return_value=response))
    clock = iter(range(20))
    monkeypatch.setattr("cluster.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("cluster.time.sleep", lambda _: None)
    with pytest.raises(TimeoutError):
        cluster.public_url(timeout=3)


def release_state():
    app = manifests(Target("kind", "staging", SHA, SHA), recommendation())[1]
    status = {
        "sync": {
            "status": "Synced",
            "revision": SHA,
            "comparedTo": {"source": deepcopy(app["spec"]["source"])},
        },
        "health": {"status": "Healthy"},
    }
    deployment = {
        "metadata": {"generation": 2},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "image": f"ghcr.io/rohitraut3366/idea-board-backend:{SHA}",
                        }
                    ]
                }
            }
        },
        "status": {"observedGeneration": 2, "updatedReplicas": 1, "availableReplicas": 1},
    }
    return app, status, deployment


@pytest.mark.parametrize(
    "stale", ["source", "revision", "image", "generation", "replicas", "health"]
)
def test_old_healthy_status_cannot_pass_new_release(monkeypatch, stale):
    app, status, deployment = release_state()
    if stale == "source":
        status["sync"]["comparedTo"]["source"]["helm"]["valuesObject"]["image"]["tag"] = "b" * 40
    elif stale == "revision":
        status["sync"]["revision"] = "b" * 40
    elif stale == "image":
        deployment["spec"]["template"]["spec"]["containers"][0]["image"] = "old:tag"
    elif stale == "generation":
        deployment["status"]["observedGeneration"] = 1
    elif stale == "replicas":
        deployment["status"]["availableReplicas"] = 0
    else:
        status["health"]["status"] = "Degraded"
    cluster = Cluster("kind-test", "idea-board-staging")
    monkeypatch.setattr(
        cluster,
        "get",
        Mock(
            side_effect=lambda kind, *args: (
                {"status": status} if kind == "application" else deployment
            )
        ),
    )
    clock = iter(range(20))
    monkeypatch.setattr("cluster.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("cluster.time.sleep", lambda _: None)
    with pytest.raises(TimeoutError):
        cluster.wait([app], timeout=3)


def test_matching_healthy_release_passes(monkeypatch):
    app, status, deployment = release_state()
    cluster = Cluster("kind-test", "idea-board-staging")
    monkeypatch.setattr(
        cluster,
        "get",
        Mock(
            side_effect=lambda kind, *args: (
                {"status": status} if kind == "application" else deployment
            )
        ),
    )
    cluster.wait([app], timeout=1)


@pytest.mark.parametrize("phase", [None, "Running", "Failed", "Succeeded"])
@pytest.mark.parametrize("matching_operation", [False, True])
def test_rollback_waits_for_its_own_successful_operation(monkeypatch, phase, matching_operation):
    app, status, deployment = release_state()
    app["operation"] = {
        "info": [{"name": "idea-board/rollback-id", "value": "current-rollback"}],
        "sync": {"revision": SHA, "syncStrategy": {"apply": {}}},
    }
    if phase:
        status["operationState"] = {
            "phase": phase,
            "operation": deepcopy(app["operation"]),
        }
        if not matching_operation:
            status["operationState"]["operation"]["info"][0]["value"] = "previous-sync"
    cluster = Cluster("kind-test", "idea-board-staging")
    monkeypatch.setattr(
        cluster,
        "get",
        Mock(
            side_effect=lambda kind, *args: (
                {"status": status} if kind == "application" else deployment
            )
        ),
    )
    clock = iter(range(20))
    monkeypatch.setattr("cluster.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("cluster.time.sleep", lambda _: None)
    if phase == "Succeeded" and matching_operation:
        cluster.wait([app], timeout=3)
    else:
        with pytest.raises(TimeoutError):
            cluster.wait([app], timeout=3)


def test_existing_unrelated_namespace_is_not_adopted(monkeypatch):
    cluster = Cluster("kind-test", "idea-board-staging")
    monkeypatch.setattr(
        cluster, "get", Mock(return_value={"metadata": {"labels": {"owner": "someone-else"}}})
    )
    apply = Mock()
    monkeypatch.setattr(cluster, "apply", apply)
    with pytest.raises(ValueError, match="not owned"):
        cluster.ensure_namespace("staging")
    apply.assert_not_called()


def test_context_is_required():
    with pytest.raises(ValueError):
        Cluster(None, "idea-board-staging")


def test_cleanup_cannot_delete_production(monkeypatch):
    from deploy import cleanup

    cluster = Cluster("kind-test", "idea-board-production")
    run = Mock()
    monkeypatch.setattr(cluster, "run", run)
    with pytest.raises(ValueError, match="restricted to previews"):
        cleanup(cluster, Target("kind", "production", SHA, SHA))
    run.assert_not_called()


def test_preview_cleanup_removes_ingress_owner_before_backend(monkeypatch):
    from deploy import cleanup

    cluster = Cluster("test", "idea-board-pr-42")
    monkeypatch.setattr(cluster, "get", Mock(return_value=None))
    run = Mock()
    monkeypatch.setattr(cluster, "run", run)
    cleanup(cluster, Target("gcp", "preview", SHA, SHA, 42))
    deleted = [entry.args[4] for entry in run.call_args_list if entry.args[3] == "application"]
    assert deleted == ["idea-board-pr-42-frontend", "idea-board-pr-42-backend"]


def test_pr_closing_during_rollout_triggers_cleanup(monkeypatch):
    from deploy import cleanup_closed_preview

    cleanup = Mock()
    monkeypatch.setattr("deploy.cleanup", cleanup)
    monkeypatch.setattr("github.api", Mock(return_value={"state": "closed"}))
    target = Target("aws", "preview", SHA, SHA, 12)
    cluster = Cluster("test", target.namespace)
    assert cleanup_closed_preview(cluster, target)
    cleanup.assert_called_once_with(cluster, target)


def test_cloud_root_wait_accepts_resolved_branch_revision(monkeypatch):
    from root import cloud_root

    target = Target("aws", "staging", SHA, SHA)
    root = cloud_root(target, manifests(target, recommendation("aws"))[1:])
    status = {
        "sync": {
            "status": "Synced",
            "revision": SHA,
            "comparedTo": {"source": deepcopy(root["spec"]["source"])},
        },
        "health": {"status": "Healthy"},
        "operationState": {"phase": "Succeeded"},
    }
    cluster = Cluster("test", target.namespace)
    monkeypatch.setattr(cluster, "get", Mock(return_value={"status": status}))
    cluster.wait([root], timeout=1)


@pytest.mark.parametrize("stale", [None, "chart_revision", "values_source"])
def test_multi_source_backend_checks_chart_revision_and_current_values(monkeypatch, stale):
    from config import chart_source

    target = Target("aws", "staging", SHA, SHA)
    app = manifests(target, recommendation("aws"))[1]
    _, _, deployment = release_state()
    status: dict = {
        "sync": {
            "status": "Synced",
            "revisions": [SHA, "c" * 40],
            "comparedTo": {"sources": deepcopy(app["spec"]["sources"])},
        },
        "health": {"status": "Healthy"},
    }
    assert chart_source(app)["targetRevision"] == SHA
    if stale == "chart_revision":
        status["sync"]["revisions"][0] = "b" * 40
    elif stale == "values_source":
        status["sync"]["comparedTo"]["sources"][1]["targetRevision"] = "old-values"
    cluster = Cluster("test", target.namespace)
    monkeypatch.setattr(
        cluster,
        "get",
        Mock(
            side_effect=lambda kind, *args: (
                {"status": status} if kind == "application" else deployment
            )
        ),
    )
    clock = iter(range(20))
    monkeypatch.setattr("cluster.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("cluster.time.sleep", lambda _: None)
    if stale:
        with pytest.raises(TimeoutError):
            cluster.wait([app], timeout=3)
    else:
        cluster.wait([app], timeout=3)
