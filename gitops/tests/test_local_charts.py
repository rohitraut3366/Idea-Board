"""Check that local overrides bootstrap the app without cloud secret APIs."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def render(chart, *arguments):
    return subprocess.run(
        ["helm", "template", "local", str(ROOT / chart), "-n", "argocd", *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_local_root_disables_external_secrets_and_creates_development_database():
    output = render("gitops/local", "-f", str(ROOT / "gitops/local/values-kind.yaml"))
    assert "name: ingress-controller" in output
    assert "name: idea-board\n" in output
    assert "name: external-secrets\n" not in output
    assert "kind: ExternalSecret" not in output and "kind: SecretStore" not in output
    assert "kind: CustomResourceDefinition" not in output
    assert "kind: PersistentVolumeClaim" in output
    assert "kind: Secret\n" in output
    assert "postgres.idea-board.svc.cluster.local:5432/idea_board" in output
    assert 'argocd.argoproj.io/sync-wave: "-1"' in output


def test_local_environment_has_two_child_applications_with_existing_chart_overrides():
    output = render("gitops/applications", "-f", str(ROOT / "gitops/applications/values-kind.yaml"))
    assert output.count("kind: Application") == 2
    for service in ("backend", "frontend"):
        assert f"name: {service}\n" in output
        assert f'path: "charts/idea-board-{service}"' in output
        assert f"../../gitops/kind/{service}-values.yaml" in output


def test_ingress_wrapper_uses_native_ingress_without_provider_crds():
    output = render("charts/ingress-controller", "--skip-crds")
    assert "kind: IngressClass" in output
    assert "kind: CustomResourceDefinition" not in output
    assert "kubernetescrd" not in output.lower()
    assert "nodePort: 30080" in output
    assert "type: NodePort" in output
