"""Verify that our umbrella chart and Argo Applications pass through overrides."""

import json
import subprocess
import tempfile
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


def render(chart, namespace, values, template=None, value_files=()):
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
    for value_file in value_files:
        command += ["--values", str(value_file)]
    return subprocess.run(
        command, input=json.dumps(values), check=True, capture_output=True, text=True
    ).stdout


class ExternalSecretsChartTests(unittest.TestCase):
    def test_generated_values_file_reaches_upstream_service_account(self):
        with tempfile.TemporaryDirectory() as directory:
            values_file = Path(directory) / "values-terraform.yaml"
            values_file.write_text(json.dumps({"external-secrets": OPERATOR_VALUES}))
            output = render(
                "charts/external-secrets",
                "external-secrets",
                {},
                "charts/external-secrets/templates/serviceaccount.yaml",
                value_files=[values_file],
            )
        self.assertIn("kind: ServiceAccount", output)
        self.assertIn("name: external-secrets-custom", output)
        self.assertIn(f"eks.amazonaws.com/role-arn: {ROLE_ARN}", output)

    def test_child_uses_the_roots_revision_and_passes_chart_overrides(self):
        output = render(
            "gitops/applications",
            "argocd",
            {
                "targetRevision": REVISION,
                "applications": {
                    "external-secrets": {
                        "enabled": True,
                        "source": {"helm": {"valuesObject": {"external-secrets": OPERATOR_VALUES}}},
                    }
                },
            },
        )
        self.assertIn(f'targetRevision: "{REVISION}"', output)
        self.assertIn('path: "charts/external-secrets"', output)
        self.assertIn("namespace: external-secrets", output)
        self.assertIn(f"eks.amazonaws.com/role-arn: {ROLE_ARN}", output)

    def test_bootstrap_passes_the_revision_and_cluster_identity_to_root(self):
        output = render(
            "infra/terraform/modules/argocd/bootstrap",
            "argocd",
            {"targetRevision": REVISION, "cloud": "aws", "clusterName": "idea-board-staging"},
            "templates/root.yaml",
        )
        self.assertEqual(output.count(f'targetRevision: "{REVISION}"'), 2)
        self.assertIn("path: gitops/applications", output)
        self.assertIn("- values-cloud.yaml", output)
        self.assertIn('cloud: "aws"', output)
        self.assertIn('clusterName: "idea-board-staging"', output)

    def test_optional_values_files_are_ordered_for_each_provider_and_cluster(self):
        for cloud in ("aws", "gcp"):
            with self.subTest(cloud=cloud):
                output = render(
                    "gitops/applications",
                    "argocd",
                    {
                        "cloud": cloud,
                        "clusterName": "idea-board-staging",
                        "applications": {"external-secrets": {"enabled": True}},
                    },
                )
                self.assertIn("ignoreMissingValueFiles: true", output)
                files = [
                    "- values.yaml",
                    f"- values/{cloud}/values.yaml",
                    f"- values/{cloud}/idea-board-staging/values.yaml",
                    f"- values/{cloud}/idea-board-staging/values-terraform.yaml",
                ]
                positions = [output.index(path) for path in files]
                self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
