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
    for service in ("backend", "frontend", "ingress-controller"):
        assert f"name: {service}\n" in output
    assert "name: external-secrets\n" not in output
    assert output.count("- values-kind.yaml") == 2
    assert output.count("- CreateNamespace=true") == 3
    assert "namespace: ingress-system" in output
    assert "namespace: idea-board" in output
    assert "kind: Deployment" not in output


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_cloud_profile_enables_only_external_secrets(cloud):
    output = render(
        "gitops/applications", "-f", str(ROOT / f"gitops/applications/values-{cloud}.yaml")
    )
    assert output.count("kind: Application") == 1
    assert "name: external-secrets\n" in output
    assert "namespace: external-secrets" in output
    assert "finalizers:" not in output
    assert "prune: true" not in output
    assert f"values/{cloud}/idea-board/values-terraform.yaml" in output


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


def test_image_tag_override_reaches_only_the_application_charts():
    output = render(
        "gitops/applications",
        "-f",
        str(ROOT / "gitops/applications/values-kind.yaml"),
        "--set",
        "imageTag=test-release",
    )
    assert output.count("tag: test-release") == 2
    ingress = next(doc for doc in output.split("---") if "name: ingress-controller\n" in doc)
    assert "image:" not in ingress


def test_ingress_wrapper_uses_native_ingress_without_provider_crds():
    output = render("charts/ingress-controller", "--skip-crds")
    assert "kind: IngressClass" in output
    assert "kind: CustomResourceDefinition" not in output
    assert "kubernetescrd" not in output.lower()
    assert "nodePort: 30080" in output
    assert "type: NodePort" in output
    assert "--providers.kubernetesingress.ingressendpoint.ip=127.0.0.1" in output


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
