"""Write reviewable application and infrastructure changes without cloud credentials."""

import json
import shlex

from config import manifests, terraform_variables


def prepare(target, recommendation, directory, recommendation_path):
    documents = manifests(target, recommendation)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "applications.json").write_text(
        json.dumps({"apiVersion": "v1", "kind": "List", "items": documents}, indent=2) + "\n"
    )
    sizing = terraform_variables(target, recommendation)
    if sizing is not None:
        (directory / "sizing.tfvars.json").write_text(json.dumps(sizing, indent=2) + "\n")
    else:
        (directory / "sizing.tfvars.json").unlink(missing_ok=True)
    plan = [
        f"# Release plan: {target.namespace}",
        f"Cloud: {target.cloud}. Image: `{target.image_tag}`. Charts: `{target.revision}`.",
        recommendation["reason"],
        "## Application changes",
    ]
    table = [
        "| Service | Replicas | CPU request | Memory request | Memory limit |",
        "| --- | --- | --- | --- | --- |",
    ]
    for service in ("backend", "frontend"):
        sizing = recommendation[service]
        table.append(
            f"| {service} | {sizing['replicas']} | {sizing['cpu_millicores']}m | "
            f"{sizing['memory_request_mib']}Mi | {sizing['memory_limit_mib']}Mi |"
        )
    plan += ["\n".join(table), "## Execution order", ""]
    plan += [
        f"{index}. {step['action']}: {step['reason']}"
        for index, step in enumerate(recommendation["steps"], 1)
    ]
    arguments = [
        "uv",
        "run",
        "--project",
        "tools/deploy",
        "python",
        "tools/deploy/deploy.py",
        "release",
        "--cloud",
        target.cloud,
        "--environment",
        target.environment,
        "--image-tag",
        target.image_tag,
        "--revision",
        target.revision,
        "--recommendation",
        str(recommendation_path),
        "--context",
        "REPLACE_WITH_CONTEXT",
    ]
    if target.pr:
        arguments += ["--pr", str(target.pr)]
    plan += [
        "",
        "After reviewing sizing and the target context, run from the repository root:",
        "",
        "```bash",
        shlex.join(arguments),
        "```",
    ]
    if recommendation["infrastructure"]:
        plan += [
            "## Infrastructure proposal",
            recommendation["infrastructure"]["reason"],
            "The release command does not apply this file. "
            "Compare it to the current stack before deployment. "
            "Database sizes may not be supported in every region; "
            "storage cannot be reduced in place. "
            "GCP node_count assumes two node_zones; adjust to your actual zone count.",
            "",
            "From an initialized Terraform root, with credentials and the existing state backend:",
            "",
            "```bash",
            f"terraform -chdir=infra/terraform/{target.cloud} plan -var-file=YOUR_STACK.tfvars "
            f"-var-file={shlex.quote(str((directory / 'sizing.tfvars.json').resolve()))}",
            "```",
            "Review the real plan before applying. This file does not replace network, "
            "identity, or database protection settings.",
        ]
    (directory / "plan.md").write_text("\n\n".join(plan) + "\n")
