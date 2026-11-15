"""Render the real Terragrunt declarations without cloud credentials."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from graphlib import TopologicalSorter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TerragruntTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.configurations = {}
        paths = [
            *ROOT.glob("*/*/*/*/terragrunt.hcl"),
            *ROOT.glob("*/*/*/applications/*/terragrunt.hcl"),
        ]
        for path in sorted(paths):
            result = subprocess.run(
                [
                    os.environ.get("TERRAGRUNT", "terragrunt"),
                    "render",
                    "--json",
                    "--working-dir",
                    str(path.parent),
                ],
                env={**os.environ, "GOOGLE_CLOUD_PROJECT": "test-project"},
                check=True,
                capture_output=True,
                text=True,
            )
            cls.configurations[path.parent] = json.loads(result.stdout)

    def test_all_projects_keep_their_existing_state_identity(self):
        self.assertEqual(len(self.configurations), 8)
        keys = set()
        for directory, config in self.configurations.items():
            with self.subTest(project=directory):
                path = directory.relative_to(ROOT)
                state = config["remote_state"]["config"]
                self.assertEqual(state["key"], f"infra/terraform/{path}.tfstate")
                self.assertEqual(state["bucket"], "idea-board-terraform-state")
                self.assertTrue(state["use_lockfile"])
                self.assertTrue(state["encrypt"])
                self.assertTrue(state["disable_bucket_update"])
                self.assertEqual(config["inputs"]["state_bucket"], state["bucket"])
                self.assertEqual(config["inputs"]["state_region"], state["region"])
                self.assertEqual(
                    config["inputs"]["state_prefix"],
                    f"infra/terraform/{Path(*path.parts[:3])}",
                )
                keys.add(state["key"])
        self.assertEqual(len(keys), 8)

    def test_shared_inputs_cover_each_project_without_tfvars(self):
        for directory, config in self.configurations.items():
            with self.subTest(project=directory):
                self.assertEqual(config["inputs"]["name"], "idea-board-staging")
                self.assertEqual(config["inputs"]["region"], directory.relative_to(ROOT).parts[2])
                if directory.relative_to(ROOT).parts[0] == "gcp":
                    self.assertEqual(config["inputs"]["project_id"], "test-project")
                self.assertNotIn("admin_role_arn", config["inputs"])

    def test_dependency_order_covers_infrastructure_and_platform(self):
        graph = {}
        for directory, config in self.configurations.items():
            dependencies = config.get("dependencies") or {}
            graph[directory] = [
                (directory / path).resolve() for path in dependencies.get("paths", [])
            ]
            self.assertTrue(all(path in self.configurations for path in graph[directory]))
        order = list(TopologicalSorter(graph).static_order())
        for cloud, region in (
            ("aws", "ap-southeast-2"),
            ("gcp", "australia-southeast1"),
        ):
            projects = [
                ROOT / cloud / "staging" / region / project
                for project in (
                    "networking",
                    "cluster",
                    "cluster-core-services",
                    "applications/idea-board",
                )
            ]
            positions = [order.index(path) for path in projects]
            self.assertEqual(positions, sorted(positions))

    def test_aws_declarations_use_the_selected_account_defaults(self):
        root = ROOT / "aws/staging/ap-southeast-2"
        cluster = self.configurations[root / "cluster"]["inputs"]
        database = self.configurations[root / "applications/idea-board"]["inputs"]
        self.assertEqual(cluster["kubernetes_version"], "1.35")
        self.assertEqual(cluster["node_instance_type"], "c7i-flex.large")
        self.assertEqual(database["database_backup_retention_days"], 0)

    def test_real_run_resolves_modules_and_ignores_legacy_tfvars(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in (
                "root.hcl",
                "state.hcl",
                "aws/staging/environment.hcl",
                "aws/staging/ap-southeast-2/region.hcl",
                "aws/staging/ap-southeast-2/networking/terragrunt.hcl",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            unit = root / "aws/staging/ap-southeast-2/networking"
            module = root / "modules/aws/network"
            module.mkdir(parents=True)
            (module / "main.tf").write_text(
                'variable "name" { type = string }\noutput "name" { value = var.name }\n'
            )
            (unit / "main.tf").write_text(
                'terraform {\n  backend "s3" {}\n}\n'
                'variable "name" { type = string }\n'
                'module "network" {\n'
                '  source = "../../../../modules/aws/network"\n'
                "  name = var.name\n}\n"
                'output "name" { value = module.network.name }\n'
            )
            (unit / "terraform.tfvars").write_text('name = "old-manual-setting"\n')
            tests = unit / "tests"
            tests.mkdir()
            (tests / "inputs.tftest.hcl").write_text(
                'run "declared_inputs" {\n'
                "  command = plan\n"
                "  assert {\n"
                '    condition = output.name == "idea-board-staging"\n'
                '    error_message = "Legacy tfvars overrode the declarations."\n'
                "  }\n}\n"
            )
            for arguments in (("init", "-backend=false", "-input=false"), ("test",)):
                result = subprocess.run(
                    [
                        os.environ.get("TERRAGRUNT", "terragrunt"),
                        "run",
                        "--no-auto-init",
                        "--working-dir",
                        str(unit),
                        "--",
                        *arguments,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
