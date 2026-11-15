from copy import deepcopy
from unittest.mock import Mock

import pytest
from recommendations import recommendation

from cluster import Cluster
from config import Target, manifests

SHA = "a" * 40


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


def test_pr_closing_during_rollout_triggers_cleanup(monkeypatch):
    from deploy import cleanup_closed_preview

    cleanup = Mock()
    monkeypatch.setattr("deploy.cleanup", cleanup)
    monkeypatch.setattr("github.api", Mock(return_value={"state": "closed"}))
    target = Target("aws", "preview", SHA, SHA, 12)
    cluster = Cluster("test", target.namespace)
    assert cleanup_closed_preview(cluster, target)
    cleanup.assert_called_once_with(cluster, target)
