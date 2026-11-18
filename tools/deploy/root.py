"""Update releases through the cloud root that owns their Applications."""

from copy import deepcopy

from config import REPOSITORY, get_application_chart_source, get_application_source_fields


def build_cloud_root_application(
    target, applications, existing_root_application=None, automated=True
):
    if not target.uses_cloud_root:
        raise ValueError("the cloud root only manages staging and production")
    root_application: dict = (
        deepcopy(existing_root_application)
        if existing_root_application
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
    root_chart_source = root_application["spec"]["source"]
    root_helm_values = root_chart_source["helm"]["valuesObject"]
    if (
        root_application["metadata"]["name"] != "idea-board"
        or root_application["spec"]["project"] != "idea-board"
        or root_application["spec"]["destination"]
        != {"server": "https://kubernetes.default.svc", "namespace": "argocd"}
        or root_chart_source["repoURL"] != REPOSITORY
        or root_chart_source["path"] != "gitops/applications"
        or root_chart_source["helm"].get("valueFiles") != [f"values-{target.cloud}.yaml"]
        or root_helm_values.get("cloud") != target.cloud
        or root_helm_values.get("clusterName") != target.namespace
    ):
        raise ValueError("cloud root does not match the requested cloud and environment")
    child_application_settings = root_helm_values.setdefault("applications", {})
    for application in applications:
        service = get_application_chart_source(application)["helm"]["releaseName"]
        child_application_settings[service] = {
            "enabled": True,
            "source": None,
            "sources": None,
            **deepcopy(get_application_source_fields(application)),
            "syncPolicy": deepcopy(application["spec"]["syncPolicy"]),
        }
    root_application["spec"]["syncPolicy"]["automated"]["enabled"] = automated
    return {
        "apiVersion": root_application["apiVersion"],
        "kind": "Application",
        "metadata": {"name": "idea-board", "namespace": "argocd"},
        "spec": root_application["spec"],
    }
