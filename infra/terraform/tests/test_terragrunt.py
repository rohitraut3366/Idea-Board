"""Render the real Terragrunt declarations without cloud credentials."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from graphlib import TopologicalSorter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TerragruntTests(unittest.TestCase):
    configurations: dict[Path, dict]
    outputs: dict

    @classmethod
    def setUpClass(cls):
        cls.configurations = {}
        paths = [
            *ROOT.glob("*/*/*/*/terragrunt.hcl"),
            *ROOT.glob("*/*/*/applications/*/terragrunt.hcl"),
        ]
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        rendered_root = Path(temporary.name)
        declarations = [
            *ROOT.glob("*.hcl"),
            *ROOT.glob("*/*/environment.hcl"),
            *ROOT.glob("*/*/*/region.hcl"),
            *paths,
        ]
        cls.outputs = {
            "aws": {
                "networking": {
                    "vpc_id": "vpc-test",
                    "private_subnet_ids": ["subnet-test-a", "subnet-test-b"],
                },
                "cluster": {
                    "cluster_name": "aws-cluster-test",
                    "node_security_group_id": "sg-test",
                },
            },
            "gcp": {
                "networking": {
                    "network_id": "projects/test-project/global/networks/test",
                    "subnetwork_id": "projects/test-project/regions/test/subnetworks/test",
                    "pods_range_name": "test-pods",
                    "services_range_name": "test-services",
                },
                "cluster": {"cluster_name": "gcp-cluster-test"},
            },
        }
        for path in declarations:
            relative = path.relative_to(ROOT)
            destination = rendered_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            text = path.read_text()
            if path.name == "terragrunt.hcl":
                outputs = cls.outputs[relative.parts[0]]

                # Mock output retrieval only in temporary test copies; deployments use real outputs.
                def mock_dependency(match: re.Match[str], outputs: dict = outputs) -> str:
                    return (
                        match[0]
                        + "\n  skip_outputs = true\n  mock_outputs = "
                        + json.dumps(outputs[match[1]])
                    )

                text = re.sub(r'dependency "(\w+)" \{', mock_dependency, text)
            destination.write_text(text)
        for path in sorted(paths):
            result = subprocess.run(
                [
                    os.environ.get("TERRAGRUNT", "terragrunt"),
                    "render",
                    "--json",
                    "--working-dir",
                    str(rendered_root / path.parent.relative_to(ROOT)),
                ],
                env={**os.environ, "GOOGLE_CLOUD_PROJECT": "test-project"},
                check=True,
                capture_output=True,
                text=True,
            )
            cls.configurations[path.parent] = json.loads(result.stdout)

    def test_all_projects_keep_their_existing_state_identity(self):
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
                keys.add(state["key"])
        self.assertEqual(len(keys), len(self.configurations))

    def test_project_inputs_resolve_shared_settings_without_tfvars(self):
        for directory, config in self.configurations.items():
            with self.subTest(project=directory):
                self.assertEqual(config["inputs"]["name"], "idea-board-staging")
                self.assertEqual(config["inputs"]["region"], directory.relative_to(ROOT).parts[2])
                if directory.relative_to(ROOT).parts[0] == "gcp":
                    self.assertEqual(config["inputs"]["project_id"], "test-project")
                self.assertIsNone(config["inputs"].get("admin_role_arn"))

    def test_dependency_order_covers_infrastructure_and_platform(self):
        graph = {}
        for directory, config in self.configurations.items():
            dependencies = config.get("dependencies") or {}
            graph[directory] = [
                (directory / path).resolve() for path in dependencies.get("paths", [])
            ]
            graph[directory] += [
                (directory / dependency["config_path"]).resolve()
                for dependency in (config.get("dependency") or {}).values()
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

    def test_dependency_outputs_are_passed_as_terraform_inputs(self):
        required_inputs = {
            "aws": {
                "cluster": {"private_subnet_ids"},
                "cluster-core-services": {"vpc_id", "cluster_name"},
                "idea-board": {
                    "vpc_id",
                    "private_subnet_ids",
                    "cluster_name",
                    "node_security_group_id",
                },
            },
            "gcp": {
                "cluster": {
                    "network_id",
                    "subnetwork_id",
                    "pods_range_name",
                    "services_range_name",
                },
                "cluster-core-services": {"cluster_name"},
                "idea-board": {"network_id", "cluster_name"},
            },
        }
        for directory, config in self.configurations.items():
            cloud = directory.relative_to(ROOT).parts[0]
            required = required_inputs[cloud].get(directory.name, set())
            expected = {
                key: value
                for outputs in self.outputs[cloud].values()
                for key, value in outputs.items()
                if key in required
            }
            with self.subTest(project=directory):
                self.assertEqual({key: config["inputs"][key] for key in required}, expected)

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
