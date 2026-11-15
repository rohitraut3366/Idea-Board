"""Check state identity and Terraform arguments without accessing cloud accounts."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("project", Path(__file__).parents[1] / "project.py")
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name).resolve()
        self.backend_config = self.repository / "infra/terraform/backend.json"

    def create(self, name):
        directory = self.repository / "infra/terraform" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "backend.tf").touch()
        config = {"bucket": "example-state", "region": "us-east-1"}
        self.backend_config.write_text(json.dumps(config))
        return directory

    def run_command(self, action, name, extra=None, environment=None):
        return project.command(self.repository, action, name, extra or [], environment or {})

    def test_aws_key_comes_from_repository_path(self):
        name = "aws/staging/ap-southeast-2/networking"
        self.create(name)
        arguments = self.run_command("init", name)
        self.assertIn(f"-backend-config=key=infra/terraform/{name}.tfstate", arguments)
        self.assertIn("-backend-config=use_lockfile=true", arguments)
        self.assertIn("-backend-config=region=us-east-1", arguments)
        plan = self.run_command("plan", name)
        self.assertIn("-var=region=ap-southeast-2", plan)
        self.assertIn("-out=project.tfplan", plan)

    def test_gcp_s3_key_and_application_dependencies(self):
        name = "gcp/staging/australia-southeast1/applications/idea-board"
        self.create(name)
        arguments = self.run_command("init", name)
        self.assertIn(f"-backend-config=key=infra/terraform/{name}.tfstate", arguments)
        plan = self.run_command("plan", name)
        self.assertIn("-var=state_bucket=example-state", plan)
        self.assertIn("-var=state_prefix=infra/terraform/gcp/staging/australia-southeast1", plan)
        self.assertIn("-var=state_region=us-east-1", plan)
        self.assertIn("-var=region=australia-southeast1", plan)

    def test_clouds_environments_and_regions_get_distinct_keys(self):
        keys = set()
        cloud_regions = {
            "aws": ("us-east-1", "ap-southeast-2"),
            "gcp": ("us-central1", "australia-southeast1"),
        }
        for cloud, regions in cloud_regions.items():
            for environment in ("staging", "production"):
                for region in regions:
                    name = f"{cloud}/{environment}/{region}/cluster"
                    self.create(name)
                    arguments = self.run_command("init", name)
                    keys.add(next(value for value in arguments if "-backend-config=key=" in value))
                    self.assertIn("-var=state_region=us-east-1", self.run_command("plan", name))
        self.assertEqual(len(keys), 8)

    def test_one_configuration_supplies_both_clouds(self):
        names = ("aws/staging/ap-southeast-2/cluster", "gcp/staging/australia-southeast1/cluster")
        for name in names:
            self.create(name)
        self.backend_config.write_text(
            json.dumps({"bucket": "central-state", "region": "eu-west-1"})
        )
        for name in names:
            with self.subTest(project=name):
                arguments = self.run_command("init", name)
                self.assertIn("-backend-config=bucket=central-state", arguments)
                self.assertIn("-backend-config=region=eu-west-1", arguments)
                self.assertIn("-backend-config=use_lockfile=true", arguments)
                plan = self.run_command("plan", name)
                self.assertIn("-var=state_bucket=central-state", plan)
                self.assertIn("-var=state_region=eu-west-1", plan)

    def test_gcp_requires_migration_from_gcs(self):
        name = "gcp/staging/australia-southeast1/cluster"
        directory = self.create(name)
        metadata = directory / ".terraform/terraform.tfstate"
        metadata.parent.mkdir()
        metadata.write_text(json.dumps({"backend": {"type": "gcs", "config": {}}}))
        with self.assertRaisesRegex(ValueError, "make init"):
            self.run_command("plan", name)
        arguments = self.run_command("init", name, ["-migrate-state", "-input=true"])
        self.assertIn("-migrate-state", arguments)
        self.assertEqual(arguments[-1], "-input=true")

    def test_rejects_nonprojects_and_path_escape(self):
        for name in (
            "",
            "../../outside",
            "modules/aws/network",
            "aws/staging/us-east-1/unknown",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.run_command("init", name)

    def test_rejects_workspace_and_changed_backend(self):
        name = "aws/staging/ap-southeast-2/cluster"
        directory = self.create(name)
        with self.assertRaisesRegex(ValueError, "default workspace"):
            self.run_command("plan", name, environment={"TF_WORKSPACE": "production"})
        metadata = directory / ".terraform/terraform.tfstate"
        metadata.parent.mkdir()
        metadata.write_text(json.dumps({"backend": {"type": "s3", "config": {"key": "old"}}}))
        with self.assertRaisesRegex(ValueError, "make init"):
            self.run_command("apply", name)

    def test_backend_cannot_supply_its_own_state_key(self):
        name = "aws/staging/ap-southeast-2/networking"
        self.create(name)
        self.backend_config.write_text(
            json.dumps({"bucket": "example", "region": "us-east-1", "key": "shared.tfstate"})
        )
        with self.assertRaises(ValueError):
            self.run_command("init", name)
        self.create(name)
        with self.assertRaisesRegex(ValueError, "project path"):
            self.run_command("init", name, ["-backend-config=key=other.tfstate"])

    def test_apply_uses_reviewed_plan_and_extra_arguments_are_preserved(self):
        name = "aws/staging/ap-southeast-2/cluster"
        self.create(name)
        self.assertEqual(self.run_command("apply", name)[-1], "project.tfplan")
        arguments = self.run_command("plan", name, ["-var-file=/path with spaces/sizing.json"])
        self.assertEqual(arguments[-1], "-var-file=/path with spaces/sizing.json")

    def test_new_application_is_declared_by_its_directory(self):
        name = "aws/staging/ap-southeast-2/applications/another-service"
        self.create(name)
        self.assertIn(
            f"-backend-config=key=infra/terraform/{name}.tfstate",
            self.run_command("init", name),
        )

    def test_make_passes_project_and_extra_arguments(self):
        executable = self.repository / "terraform-stub"
        executable.write_text(
            "#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n"
        )
        executable.chmod(0o755)
        repository = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            [
                "make",
                "test",
                "PROJECT=aws/staging/ap-southeast-2/networking",
                f"TERRAFORM={executable}",
                "ARGS=-no-color",
            ],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
        arguments = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(arguments[1:], ["test", "-no-color"])
        self.assertEqual(
            arguments[0],
            f"-chdir={repository}/infra/terraform/aws/staging/ap-southeast-2/networking",
        )

    def test_validation_does_not_need_backend_configuration(self):
        name = "aws/staging/ap-southeast-2/networking"
        self.create(name)
        self.backend_config.unlink()
        self.assertEqual(self.run_command("test", name)[-1], "test")


if __name__ == "__main__":
    unittest.main()
