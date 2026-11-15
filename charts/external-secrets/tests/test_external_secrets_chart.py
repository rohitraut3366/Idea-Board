"""Verify that our umbrella chart and Argo Applications pass through overrides."""

import json
import subprocess
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
ROLE_ARN = "arn:aws:iam::123456789012:role/external-secrets"
REVISION = "a" * 40
OPERATOR_VALUES = {
    "serviceAccount": {
        "name": "external-secrets-custom",
        "annotations": {"eks.amazonaws.com/role-arn": ROLE_ARN},
    }
}


def render(chart, namespace, values, template=None):
    command = [
        "helm",
        "template",
        "external-secrets",
        str(REPOSITORY / chart),
        "--namespace",
        namespace,
        "--values",
        "-",
    ]
    if template:
        command += ["--show-only", template]
    return subprocess.run(
        command, input=json.dumps(values), check=True, capture_output=True, text=True
    ).stdout


class ExternalSecretsChartTests(unittest.TestCase):
    def test_iam_annotation_reaches_upstream_service_account(self):
        output = render(
            "charts/external-secrets",
            "external-secrets",
            {"external-secrets": OPERATOR_VALUES},
            "charts/external-secrets/templates/serviceaccount.yaml",
        )
        self.assertIn("kind: ServiceAccount", output)
        self.assertIn("name: external-secrets-custom", output)
        self.assertIn(f"eks.amazonaws.com/role-arn: {ROLE_ARN}", output)

    def test_child_uses_the_roots_revision_and_passes_chart_overrides(self):
        output = render(
            "gitops/cluster-core-services",
            "argocd",
            {
                "targetRevision": REVISION,
                "applications": {
                    "external-secrets": {"values": {"external-secrets": OPERATOR_VALUES}}
                },
            },
        )
        self.assertIn(f'targetRevision: "{REVISION}"', output)
        self.assertIn('path: "charts/external-secrets"', output)
        self.assertIn("namespace: external-secrets", output)
        self.assertIn(f"eks.amazonaws.com/role-arn: {ROLE_ARN}", output)

    def test_bootstrap_passes_the_revision_and_iam_override_to_root(self):
        output = render(
            "infra/terraform/modules/argocd/bootstrap",
            "argocd",
            {"targetRevision": REVISION, "externalSecrets": OPERATOR_VALUES},
            "templates/root.yaml",
        )
        self.assertEqual(output.count(f'targetRevision: "{REVISION}"'), 2)
        self.assertIn("path: gitops/cluster-core-services", output)
        self.assertIn(f"eks.amazonaws.com/role-arn: {ROLE_ARN}", output)


if __name__ == "__main__":
    unittest.main()
