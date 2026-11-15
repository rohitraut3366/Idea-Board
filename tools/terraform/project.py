"""Run Terraform for a project whose repository path determines its state location."""

import argparse
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
ACTIONS = ("init", "plan", "apply", "output", "destroy", "state", "validate", "test")


def project_directory(repository, project):
    base = repository / "infra/terraform"
    directory = (base / project).resolve()
    relative = directory.relative_to(base.resolve())
    parts = relative.parts
    if (
        len(parts) not in (4, 5)
        or parts[0] not in ("aws", "gcp")
        or parts[1] not in ("staging", "production")
        or not all(re.fullmatch(r"[a-z][a-z0-9-]+", part) for part in parts[2:])
        or (len(parts) == 5 and parts[3] != "applications")
        or (len(parts) == 4 and parts[3] == "applications")
        or not (directory / "backend.tf").is_file()
    ):
        raise ValueError(
            "PROJECT must select cloud/environment/region/project under infra/terraform."
        )
    return directory, parts


def command(repository, action, project, extra, environment):
    directory, parts = project_directory(repository, project)
    cloud, _, region = parts[:3]
    workspace = directory / ".terraform/environment"
    if environment.get("TF_WORKSPACE", "default") != "default" or (
        workspace.exists() and workspace.read_text().strip() != "default"
    ):
        raise ValueError(
            "Use the default workspace; environments have separate project directories."
        )
    arguments = [
        environment.get("TERRAFORM", "terraform"),
        f"-chdir={directory}",
        action,
    ]
    if action in ("validate", "test"):
        return arguments + extra

    region_directory = repository / "infra/terraform" / Path(*parts[:3])
    config_path = region_directory / "backend.json"
    config = json.loads(config_path.read_text())
    allowed = {"bucket", "region"} if cloud == "aws" else {"bucket"}
    if config.keys() - allowed or not isinstance(config.get("bucket"), str):
        raise ValueError(
            f"{config_path} must contain bucket" + (" and region." if cloud == "aws" else ".")
        )
    if not config["bucket"] or config["bucket"].startswith("replace-"):
        raise ValueError(f"Set the state bucket in {config_path}.")
    if cloud == "aws" and not isinstance(config.get("region"), str):
        raise ValueError(f"Set the state bucket region in {config_path}.")

    prefix = directory.relative_to(repository).as_posix()
    backend = dict(config)
    backend["key" if cloud == "aws" else "prefix"] = (
        f"{prefix}.tfstate" if cloud == "aws" else prefix
    )
    if cloud == "aws":
        backend["use_lockfile"] = True
    print(
        f"Project: {project}\nState: {config['bucket']}/{backend.get('key', prefix)}",
        flush=True,
    )
    if action == "init":
        if any(value.startswith("-backend-config") for value in extra):
            raise ValueError("Backend settings come from backend.json and the project path.")
        arguments += ["-input=false", "-lockfile=readonly"]
        arguments += [
            f"-backend-config={key}={str(value).lower() if isinstance(value, bool) else value}"
            for key, value in backend.items()
        ]
    else:
        metadata = directory / ".terraform/terraform.tfstate"
        if metadata.exists():
            initialized = json.loads(metadata.read_text()).get("backend", {})
            expected_type = "s3" if cloud == "aws" else "gcs"
            if initialized.get("type") != expected_type or any(
                initialized.get("config", {}).get(key) != value for key, value in backend.items()
            ):
                raise ValueError("Backend settings changed. Run make init for this project first.")
        if action in ("plan", "destroy"):
            arguments += [f"-var=region={region}"]
            if parts[3] != "networking":
                state_prefix = region_directory.relative_to(repository).as_posix()
                arguments += [
                    f"-var=state_bucket={config['bucket']}",
                    f"-var=state_prefix={state_prefix}",
                ]
                if cloud == "aws":
                    arguments += [f"-var=state_region={config['region']}"]
        if action == "plan":
            arguments += ["-input=false", "-out=project.tfplan"]
        elif action == "apply":
            arguments += ["project.tfplan"]
    if action == "apply":
        return arguments[:-1] + extra + arguments[-1:]
    return arguments + extra


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("project")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    extra = args.arguments
    if extra[:1] == ["--"]:
        extra = extra[1:]
    try:
        arguments = command(REPOSITORY, args.action, args.project, extra, os.environ)
        print(shlex.join(arguments), flush=True)
        result = subprocess.run(arguments, check=False)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
