"""Write reviewable application and infrastructure changes without cloud credentials."""

import json
import shlex

from config import deployment_manifests, terraform_variables


def prepare(target, recommendation, directory, recommendation_path):
    documents = deployment_manifests(target, recommendation)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "applications.json").write_text(
        json.dumps({"apiVersion": "v1", "kind": "List", "items": documents}, indent=2) + "\n"
    )
    sizing = terraform_variables(target, recommendation)
    (directory / "sizing.tfvars.json").unlink(missing_ok=True)
    for project in ("cluster", "applications/idea-board"):
        path = directory / "terraform" / project / "sizing.tfvars.json"
        if sizing is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(sizing[project], indent=2) + "\n")
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
            "The release command does not apply infrastructure changes. "
            "Compare each proposal to its current project before deployment. "
            "Database sizes may not be supported in every region; "
            "storage cannot be reduced in place. "
            "GCP node_count assumes two node_zones; adjust to your actual zone count.",
            "",
            "From the repository root, replace YOUR_REGION with the target region. "
            "Terragrunt loads the project's declared inputs and state configuration:",
        ]
        for project in ("cluster", "applications/idea-board"):
            path = directory / "terraform" / project / "sizing.tfvars.json"
            plan += [
                "```bash",
                "terragrunt run "
                f"--working-dir infra/terraform/{target.cloud}/"
                f"{target.environment}/YOUR_REGION/{project} -- plan "
                f"{shlex.quote('-var-file=' + str(path.resolve()))} -out=project.tfplan",
                "```",
            ]
        plan += [
            "Review and apply each project separately. The proposals do not replace network, "
            "identity, or database protection settings."
        ]
    (directory / "plan.md").write_text("\n\n".join(plan) + "\n")
