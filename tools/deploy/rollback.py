"""Restore a verified Argo source; never downgrade a database or use rollout undo."""

import json
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

from config import (
    REPOSITORY,
    build_environment_parent_application,
    get_application_chart_source,
    get_application_source_fields,
)
from root import build_cloud_root_application

STATE_NAME = "idea-board-release"


def read_release_state(cluster):
    release_state_configmap = cluster.get_resource("configmap", STATE_NAME, cluster.namespace)
    if not release_state_configmap:
        return {"healthy": None, "attempt": None}
    if (
        release_state_configmap["metadata"].get("labels", {}).get("app.kubernetes.io/part-of")
        != "idea-board"
    ):
        raise ValueError("release state is not owned by Idea Board")
    return json.loads(release_state_configmap["data"]["release.json"])


def save_release_state(cluster, release_state):
    cluster.apply_resource(
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


def record_release_attempt(cluster, target, applications):
    release_state = read_release_state(cluster)
    release_state["attempt"] = {
        "image_tag": target.image_tag,
        "revision": target.revision,
        "applications": applications,
    }
    save_release_state(cluster, release_state)


def record_healthy_release(cluster, applications):
    save_release_state(cluster, {"healthy": applications, "attempt": None})


def rollback(cluster, target, schema_compatible):
    if not schema_compatible:
        raise ValueError("confirm the previous code supports the current database schema")
    cluster.ensure_namespace(target.environment)
    release_state = read_release_state(cluster)
    healthy_applications = release_state["healthy"]
    release_attempt = release_state["attempt"]
    if not healthy_applications or not release_attempt:
        raise ValueError("no failed attempt with a previously verified release is available")
    if (
        release_attempt["image_tag"] != target.image_tag
        or release_attempt["revision"] != target.revision
    ):
        raise ValueError("rollback target does not match the latest attempted release")
    restored_applications = deepcopy(healthy_applications)
    # Validate both Applications before changing either one.
    for service, application, attempted_application in zip(
        ("backend", "frontend"), restored_applications, release_attempt["applications"], strict=True
    ):
        application_name = f"{target.namespace}-{service}"
        healthy_chart_source = get_application_chart_source(application)
        if (
            application["kind"] != "Application"
            or application["metadata"]["name"] != application_name
            or application["metadata"]["namespace"] != "argocd"
            or application["spec"]["project"]
            != ("idea-board" if target.uses_cloud_root else target.namespace)
            or application["spec"]["destination"]
            != {
                "server": "https://kubernetes.default.svc",
                "namespace": target.namespace,
            }
            or healthy_chart_source["repoURL"] != REPOSITORY
            or healthy_chart_source["path"] != f"charts/idea-board-{service}"
        ):
            raise ValueError("checkpoint does not belong to the requested release")
        current_application = cluster.get_resource("application", application_name, "argocd")
        if not current_application or get_application_source_fields(current_application) not in (
            get_application_source_fields(application),
            get_application_source_fields(attempted_application),
        ):
            raise ValueError(
                "Application changed since the failed attempt; inspect before rollback"
            )
        sync_operation_phase = (
            current_application.get("status", {}).get("operationState", {}).get("phase")
        )
        if current_application.get("operation") or sync_operation_phase in {
            "Running",
            "Terminating",
        }:
            raise ValueError("Argo sync is still running; terminate it in Argo CD before rollback")
        # Automatic sync runs hooks. Keep it paused until the next regular release.
        application["spec"]["syncPolicy"]["automated"]["enabled"] = False
        application["operation"] = {
            "info": [{"name": "idea-board/rollback-id", "value": str(uuid4())}],
            "sync": {
                "revision": healthy_chart_source["targetRevision"],
                "syncStrategy": {"apply": {}},
            },
        }
        if "sources" in application["spec"]:
            application["operation"]["sync"].pop("revision")
            application["operation"]["sync"]["revisions"] = [
                child_application_config["targetRevision"]
                for child_application_config in application["spec"]["sources"]
            ]
    if target.cloud == "kind":
        parent_application = cluster.get_resource("application", target.namespace, "argocd")
        allowed_child_application_sets = [
            healthy_applications,
            release_attempt["applications"],
            [release_attempt["applications"][0], healthy_applications[1]],
        ]
        allowed_chart_revisions = {
            target.revision,
            get_application_chart_source(healthy_applications[0])["targetRevision"],
        }
        allowed_parent_sources = [
            build_environment_parent_application(replace(target, revision=revision), applications)[
                "spec"
            ]["source"]
            for revision in allowed_chart_revisions
            for applications in allowed_child_application_sets
        ]
        if (
            not parent_application
            or parent_application["spec"]["source"] not in allowed_parent_sources
        ):
            raise ValueError("parent Application changed since the failed attempt")
        if parent_application.get("operation") or parent_application.get("status", {}).get(
            "operationState", {}
        ).get("phase") in {"Running", "Terminating"}:
            raise ValueError("parent Argo sync is still running; inspect before rollback")
        # Pause its reconciliation before restoring children it normally owns.
        parent_application["spec"]["syncPolicy"]["automated"]["enabled"] = False
        cluster.apply_resource(
            {
                "apiVersion": parent_application["apiVersion"],
                "kind": "Application",
                "metadata": {"name": target.namespace, "namespace": "argocd"},
                "spec": parent_application["spec"],
            }
        )
    elif target.uses_cloud_root:
        current_application = cluster.get_resource("application", "idea-board", "argocd")
        if not current_application:
            raise ValueError("cloud root is missing; inspect before rollback")
        parent_application = build_cloud_root_application(
            target, [], current_application, automated=False
        )
        child_application_settings = parent_application["spec"]["source"]["helm"][
            "valuesObject"
        ].get("applications", {})
        for healthy_application, attempted_application in zip(
            healthy_applications, release_attempt["applications"], strict=True
        ):
            service = get_application_chart_source(healthy_application)["helm"]["releaseName"]
            child_application_config = child_application_settings.get(service, {})
            configured_source_fields = {
                key: child_application_config[key]
                for key in ("source", "sources")
                if child_application_config.get(key) is not None
            }
            if configured_source_fields not in (
                get_application_source_fields(healthy_application),
                get_application_source_fields(attempted_application),
            ):
                raise ValueError("cloud root changed since the failed attempt")
        if current_application.get("operation") or current_application.get("status", {}).get(
            "operationState", {}
        ).get("phase") in {"Running", "Terminating"}:
            raise ValueError("cloud root sync is still running; inspect before rollback")
        cluster.apply_resource(parent_application)
    for application in restored_applications:
        # The parent owns these fields through SSA; takeover follows the drift guards above.
        cluster.apply_resource(application, force=target.cloud == "kind" or target.uses_cloud_root)
        cluster.wait_for_application_health([application])
        # An operation is a one-time request, not part of a release checkpoint.
        del application["operation"]
    if target.cloud == "kind" or target.uses_cloud_root:
        restored_target = replace(
            target, revision=get_application_chart_source(healthy_applications[0])["targetRevision"]
        )
        parent_application = (
            build_cloud_root_application(
                restored_target, restored_applications, parent_application, automated=False
            )
            if target.uses_cloud_root
            else build_environment_parent_application(
                restored_target, restored_applications, automated=False
            )
        )
        parent_application["operation"] = {
            "info": [{"name": "idea-board/rollback-id", "value": str(uuid4())}],
            "sync": {
                "revision": parent_application["spec"]["source"]["targetRevision"],
                "syncStrategy": {"apply": {}},
            },
        }
        cluster.apply_resource(parent_application)
        cluster.wait_for_application_health([parent_application])
    cluster.verify_application_http()
    if target.cloud != "kind":
        cluster.wait_for_public_http()
    record_healthy_release(cluster, restored_applications)
    return {
        "status": "rolled_back",
        "namespace": target.namespace,
        "restored_images": [
            get_application_chart_source(application)["helm"]["valuesObject"]["image"]
            for application in restored_applications
        ],
    }
