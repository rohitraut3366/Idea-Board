"""Restore a verified Argo source; never downgrade a database or use rollout undo."""

import json
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

from config import REPOSITORY, parent_application
from root import cloud_root

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
            or application["spec"]["project"]
            != ("idea-board" if target.uses_cloud_root else target.namespace)
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
    if target.cloud == "kind":
        parent = cluster.get("application", target.namespace, "argocd")
        children = [previous, attempt["applications"], [attempt["applications"][0], previous[1]]]
        revisions = {target.revision, previous[0]["spec"]["source"]["targetRevision"]}
        allowed_sources = [
            parent_application(replace(target, revision=revision), applications)["spec"]["source"]
            for revision in revisions
            for applications in children
        ]
        if not parent or parent["spec"]["source"] not in allowed_sources:
            raise ValueError("parent Application changed since the failed attempt")
        if parent.get("operation") or parent.get("status", {}).get("operationState", {}).get(
            "phase"
        ) in {"Running", "Terminating"}:
            raise ValueError("parent Argo sync is still running; inspect before rollback")
        # Pause its reconciliation before restoring children it normally owns.
        parent["spec"]["syncPolicy"]["automated"]["enabled"] = False
        cluster.apply(
            {
                "apiVersion": parent["apiVersion"],
                "kind": "Application",
                "metadata": {"name": target.namespace, "namespace": "argocd"},
                "spec": parent["spec"],
            }
        )
    elif target.uses_cloud_root:
        current = cluster.get("application", "idea-board", "argocd")
        if not current:
            raise ValueError("cloud root is missing; inspect before rollback")
        parent = cloud_root(target, [], current, automated=False)
        entries = parent["spec"]["source"]["helm"]["valuesObject"].get("applications", {})
        for old, attempted in zip(previous, attempt["applications"], strict=True):
            service = old["spec"]["source"]["helm"]["releaseName"]
            if entries.get(service, {}).get("source") not in (
                old["spec"]["source"],
                attempted["spec"]["source"],
            ):
                raise ValueError("cloud root changed since the failed attempt")
        if current.get("operation") or current.get("status", {}).get("operationState", {}).get(
            "phase"
        ) in {"Running", "Terminating"}:
            raise ValueError("cloud root sync is still running; inspect before rollback")
        cluster.apply(parent)
    for application in restored:
        # The parent owns these fields through SSA; takeover follows the drift guards above.
        cluster.apply(application, force=target.cloud == "kind" or target.uses_cloud_root)
        cluster.wait([application])
        # An operation is a one-time request, not part of a release checkpoint.
        del application["operation"]
    if target.cloud == "kind" or target.uses_cloud_root:
        restored_target = replace(target, revision=previous[0]["spec"]["source"]["targetRevision"])
        parent = (
            cloud_root(restored_target, restored, parent, automated=False)
            if target.uses_cloud_root
            else parent_application(restored_target, restored, automated=False)
        )
        parent["operation"] = {
            "info": [{"name": "idea-board/rollback-id", "value": str(uuid4())}],
            "sync": {
                "revision": parent["spec"]["source"]["targetRevision"],
                "syncStrategy": {"apply": {}},
            },
        }
        cluster.apply(parent)
        cluster.wait([parent])
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
