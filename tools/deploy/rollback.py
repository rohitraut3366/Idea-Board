"""Restore a verified Argo source; never downgrade a database or use rollout undo."""

import json
from copy import deepcopy
from uuid import uuid4

from config import REPOSITORY

STATE_NAME = "idea-board-release"


def state(cluster):
    document = cluster.get("configmap", STATE_NAME, cluster.namespace)
    if not document:
        return {"healthy": None, "attempt": None}
    if document["metadata"].get("labels", {}).get("app.kubernetes.io/part-of") != "idea-board":
        raise ValueError("release state is not owned by Idea Board")
    return json.loads(document["data"]["release.json"])


def save(cluster, release_state):
    cluster.apply(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": STATE_NAME,
                "namespace": cluster.namespace,
                "labels": {"app.kubernetes.io/part-of": "idea-board"},
            },
            "data": {"release.json": json.dumps(release_state)},
        }
    )


def checkpoint(cluster, target, applications):
    release_state = state(cluster)
    release_state["attempt"] = {
        "image_tag": target.image_tag,
        "revision": target.revision,
        "applications": applications,
    }
    save(cluster, release_state)


def record_healthy(cluster, applications):
    save(cluster, {"healthy": applications, "attempt": None})


def rollback(cluster, target, schema_compatible):
    if not schema_compatible:
        raise ValueError("confirm the previous code supports the current database schema")
    cluster.ensure_namespace(target.environment)
    release_state = state(cluster)
    previous = release_state["healthy"]
    attempt = release_state["attempt"]
    if not previous or not attempt:
        raise ValueError("no failed attempt with a previously verified release is available")
    if attempt["image_tag"] != target.image_tag or attempt["revision"] != target.revision:
        raise ValueError("rollback target does not match the latest attempted release")
    restored = deepcopy(previous)
    # Validate both Applications before changing either one.
    for service, application, attempted in zip(
        ("backend", "frontend"), restored, attempt["applications"], strict=True
    ):
        name = f"{target.namespace}-{service}"
        source = application["spec"]["source"]
        if (
            application["kind"] != "Application"
            or application["metadata"]["name"] != name
            or application["metadata"]["namespace"] != "argocd"
            or application["spec"]["project"] != target.namespace
            or application["spec"]["destination"]
            != {
                "server": "https://kubernetes.default.svc",
                "namespace": target.namespace,
            }
            or source["repoURL"] != REPOSITORY
            or source["path"] != f"charts/idea-board-{service}"
        ):
            raise ValueError("checkpoint does not belong to the requested release")
        current = cluster.get("application", name, "argocd")
        if not current or current["spec"]["source"] not in (source, attempted["spec"]["source"]):
            raise ValueError(
                "Application changed since the failed attempt; inspect before rollback"
            )
        phase = current.get("status", {}).get("operationState", {}).get("phase")
        if current.get("operation") or phase in {
            "Running",
            "Terminating",
        }:
            raise ValueError("Argo sync is still running; terminate it in Argo CD before rollback")
        # Automatic sync runs hooks. Keep it paused until the next regular release.
        application["spec"]["syncPolicy"]["automated"]["enabled"] = False
        application["operation"] = {
            "info": [{"name": "idea-board/rollback-id", "value": str(uuid4())}],
            "sync": {
                "revision": source["targetRevision"],
                "syncStrategy": {"apply": {}},
            },
        }
    for application in restored:
        cluster.apply(application)
        cluster.wait([application])
        # An operation is a one-time request, not part of a release checkpoint.
        del application["operation"]
    cluster.verify()
    if target.cloud != "kind":
        cluster.public_url()
    record_healthy(cluster, restored)
    return {
        "status": "rolled_back",
        "namespace": target.namespace,
        "restored_images": [
            app["spec"]["source"]["helm"]["valuesObject"]["image"] for app in restored
        ],
    }
