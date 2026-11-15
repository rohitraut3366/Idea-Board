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

    def create(self, name):
        directory = self.repository / "infra/terraform" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "backend.tf").touch()
        parts = name.split("/")
        config = {"bucket": "example-state"}
        if parts[0] == "aws":
            config["region"] = "us-east-1"
        region_directory = self.repository / "infra/terraform" / Path(*parts[:3])
        (region_directory / "backend.json").write_text(json.dumps(config))
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

    def test_gcp_prefix_and_application_dependencies(self):
        name = "gcp/staging/australia-southeast1/applications/idea-board"
        self.create(name)
        arguments = self.run_command("init", name)
        self.assertIn(f"-backend-config=prefix=infra/terraform/{name}", arguments)
        plan = self.run_command("plan", name)
        self.assertIn("-var=state_bucket=example-state", plan)
        self.assertIn("-var=state_prefix=infra/terraform/gcp/staging/australia-southeast1", plan)
        self.assertFalse(any("state_region" in value for value in plan))

    def test_environments_and_regions_get_distinct_keys(self):
        keys = set()
        for environment in ("staging", "production"):
            for region in ("us-east-1", "ap-southeast-2"):
                name = f"aws/{environment}/{region}/cluster"
                self.create(name)
                arguments = self.run_command("init", name)
                keys.add(next(value for value in arguments if "-backend-config=key=" in value))
                self.assertIn("-var=state_region=us-east-1", self.run_command("plan", name))
        self.assertEqual(len(keys), 4)

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
        directory = self.create(name)
        (directory.parent / "backend.json").write_text(
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
        directory = self.create(name)
        (directory.parent / "backend.json").unlink()
        self.assertEqual(self.run_command("test", name)[-1], "test")


if __name__ == "__main__":
    unittest.main()
