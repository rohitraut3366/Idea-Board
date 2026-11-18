"""Update releases through the cloud root that owns their Applications."""

from copy import deepcopy

from config import REPOSITORY, chart_source, source_fields


def cloud_root(target, applications, current=None):
    if not target.uses_cloud_root:
        raise ValueError("the cloud root only manages staging and production")
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
                        "valuesObject": {"cloud": target.cloud, "clusterName": target.namespace},
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
        or values.get("clusterName") != target.namespace
    ):
        raise ValueError("cloud root does not match the requested cloud and environment")
    children = values.setdefault("applications", {})
    for application in applications:
        service = chart_source(application)["helm"]["releaseName"]
        children[service] = {
            "enabled": True,
            "source": None,
            "sources": None,
            **deepcopy(source_fields(application)),
            "syncPolicy": deepcopy(application["spec"]["syncPolicy"]),
        }
    return {
        "apiVersion": root["apiVersion"],
        "kind": "Application",
        "metadata": {"name": "idea-board", "namespace": "argocd"},
        "spec": root["spec"],
    }
