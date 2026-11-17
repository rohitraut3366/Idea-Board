"""Check that local overrides bootstrap the app without cloud secret APIs."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def render(chart, *arguments):
    return subprocess.run(
        ["helm", "template", "local", str(ROOT / chart), "-n", "argocd", *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_root_defaults_deploy_nothing():
    assert not render("gitops/applications").strip()


def test_kind_profile_enables_only_ingress_and_application_services():
    output = render("gitops/applications", "-f", str(ROOT / "gitops/applications/values-kind.yaml"))
    assert output.count("kind: Application") == 3
    assert output.count("- resources-finalizer.argocd.argoproj.io") == 3
    for service in ("backend", "frontend", "ingress-controller"):
        assert f"name: {service}\n" in output
    assert "name: external-secrets\n" not in output
    assert output.count("- values-kind.yaml") == 2
    assert output.count("- CreateNamespace=true") == 3
    assert "namespace: ingress-system" in output
    assert "namespace: idea-board" in output
    assert "kind: Deployment" not in output


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_cloud_profile_enables_operator_and_environment_services(cloud):
    output = render(
        "gitops/applications",
        "-f",
        str(ROOT / f"gitops/applications/values-{cloud}.yaml"),
        "--set",
        "clusterName=idea-board-staging",
    )
    assert output.count("kind: Application") == 3
    assert output.count("- resources-finalizer.argocd.argoproj.io") == 3
    operator = next(doc for doc in output.split("---") if "name: external-secrets\n" in doc)
    assert "namespace: external-secrets" in operator
    assert "prune: true" not in operator
    assert f"values/{cloud}/idea-board-staging/values-terraform.yaml" in operator
    for service in ("backend", "frontend"):
        child = next(
            doc for doc in output.split("---") if f"name: idea-board-staging-{service}\n" in doc
        )
        assert "namespace: idea-board-staging" in child
        assert f"- values-{cloud}.yaml" in child
        assert "managedNamespaceMetadata:" in child


def test_values_can_disable_apps_and_enable_another_service():
    output = render(
        "gitops/applications",
        "-f",
        str(ROOT / "gitops/applications/values-kind.yaml"),
        "--set",
        "applications.frontend.enabled=false",
        "--set",
        "applications.external-secrets.enabled=true",
    )
    assert "name: frontend\n" not in output
    assert "name: external-secrets\n" in output
    assert "name: backend\n" in output


def test_child_helm_values_keep_independent_image_tags():
    output = render(
        "gitops/applications",
        "-f",
        str(ROOT / "gitops/applications/values-kind.yaml"),
        "--set",
        "applications.backend.source.helm.valuesObject.image.tag=backend-release",
        "--set",
        "applications.frontend.source.helm.valuesObject.image.tag=frontend-release",
    )
    backend = next(doc for doc in output.split("---") if "name: backend\n" in doc)
    frontend = next(doc for doc in output.split("---") if "name: frontend\n" in doc)
    assert "tag: backend-release" in backend
    assert "tag: frontend-release" in frontend
    ingress = next(doc for doc in output.split("---") if "name: ingress-controller\n" in doc)
    assert "image:" not in ingress


@pytest.mark.parametrize("cloud", ["kind", "aws", "gcp"])
def test_same_bootstrap_selects_the_cloud_profile_and_reconciles_applications(cloud):
    output = render("infra/terraform/modules/argocd/bootstrap", "--set", f"cloud={cloud}")
    root = next(document for document in output.split("---") if "\nkind: Application\n" in document)
    assert "name: idea-board" in root
    assert "path: gitops/applications" in root
    assert f"- values-{cloud}.yaml" in root
    assert f'cloud: "{cloud}"' in root
    assert "prune: true" in root
    assert "- ServerSideApply=true" in root
