"""Update environment Applications through the existing shared root."""

from copy import deepcopy

from config import REPOSITORY, chart_source, source_fields


def shared_root(target, applications, current=None):
    root: dict = (
        deepcopy(current)
        if current
        else {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "metadata": {"name": "idea-board", "namespace": "argocd"},
            "spec": {
                "project": "idea-board",
                "source": {
                    "repoURL": REPOSITORY,
                    "targetRevision": "master",
                    "path": "gitops/applications",
                    "helm": {
                        "valueFiles": [f"values-{target.cloud}.yaml"],
                        "valuesObject": {
                            "cloud": target.cloud,
                            "clusterName": target.namespace
                            if target.uses_managed_database
                            else "idea-board",
                        },
                    },
                },
                "destination": {"server": "https://kubernetes.default.svc", "namespace": "argocd"},
                "syncPolicy": {
                    "automated": {"prune": True, "selfHeal": True},
                    "syncOptions": ["ServerSideApply=true"],
                },
            },
        }
    )
    source = root["spec"]["source"]
    values = source["helm"]["valuesObject"]
    if (
        root["metadata"]["name"] != "idea-board"
        or root["spec"]["project"] != "idea-board"
        or root["spec"]["destination"]
        != {"server": "https://kubernetes.default.svc", "namespace": "argocd"}
        or source["repoURL"] != REPOSITORY
        or source["path"] != "gitops/applications"
        or source["helm"].get("valueFiles") != [f"values-{target.cloud}.yaml"]
        or values.get("cloud") != target.cloud
        or (target.uses_managed_database and values.get("clusterName") != target.namespace)
    ):
        raise ValueError("shared root does not match the requested cloud and environment")
    children = values.setdefault("applications", {})
    for application in applications:
        service = chart_source(application)["helm"]["releaseName"]
        children[application_key(target, service)] = {
            "name": application["metadata"]["name"],
            "namespace": application["spec"]["destination"]["namespace"],
            "project": application["spec"]["project"],
            "enabled": True,
            "source": None,
            "sources": None,
            **deepcopy(source_fields(application)),
            "syncPolicy": deepcopy(application["spec"]["syncPolicy"]),
        }
    root["spec"]["syncPolicy"].setdefault("automated", {})["enabled"] = True
    return {
        "apiVersion": root["apiVersion"],
        "kind": "Application",
        "metadata": {
            "name": "idea-board",
            "namespace": "argocd",
            **(
                {"resourceVersion": current["metadata"]["resourceVersion"]}
                if current and "resourceVersion" in current["metadata"]
                else {}
            ),
        },
        "spec": root["spec"],
    }


def application_key(target, service):
    return service if target.uses_managed_database else f"{target.namespace}-{service}"


def existing_root(cluster, target):
    current = cluster.get("application", "idea-board", "argocd")
    if not current:
        raise ValueError("install the shared idea-board root before deploying environments")
    shared_root(target, [], current)
    return current


def environment_root(cluster, target):
    """Preserve existing children and orphan a previous kind environment parent."""
    root = existing_root(cluster, target)
    parent = (
        cluster.get("application", target.namespace, "argocd") if target.cloud == "kind" else None
    )
    if parent:
        source = parent["spec"].get("source", {})
        values = source.get("helm", {}).get("valuesObject", {})
        if (
            parent["spec"].get("project") != target.namespace
            or source.get("repoURL") != REPOSITORY
            or source.get("path") != "gitops/applications"
            or values.get("namespace") != target.namespace
            or values.get("namePrefix") != target.namespace + "-"
        ):
            raise ValueError("existing environment parent is not owned by this deployment tool")
        if parent.get("operation") or parent.get("status", {}).get("operationState", {}).get(
            "phase"
        ) in {"Running", "Terminating"}:
            raise ValueError("environment parent is still syncing; retry after it finishes")
    entries = root["spec"]["source"]["helm"]["valuesObject"].get("applications", {})
    children = []
    for service in ("backend", "frontend"):
        if application_key(target, service) in entries:
            continue
        child = cluster.get("application", f"{target.namespace}-{service}", "argocd")
        if child:
            source = chart_source(child)
            if (
                child["spec"]["destination"]
                != {"server": "https://kubernetes.default.svc", "namespace": target.namespace}
                or child["spec"]["project"]
                != ("idea-board" if target.uses_managed_database else target.namespace)
                or source.get("repoURL") != REPOSITORY
                or source.get("path") != f"charts/idea-board-{service}"
            ):
                raise ValueError("existing child Application does not match the requested target")
            children.append(child)
    if parent:
        # The Argo finalizer controls cascading deletion; remove it before orphaning
        # the old grouping Application. Child Applications and their data stay intact.
        cluster.run(
            "--namespace",
            "argocd",
            "patch",
            "application",
            target.namespace,
            "--type=merge",
            "-p",
            '{"metadata":{"finalizers":[]},"spec":{"syncPolicy":{"automated":{"enabled":false}}}}',
        )
        cluster.run(
            "--namespace",
            "argocd",
            "delete",
            "application",
            target.namespace,
            "--cascade=orphan",
            "--wait=true",
            "--timeout=1m",
        )
    return shared_root(target, children, root)
