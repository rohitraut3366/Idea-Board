"""Write reviewable application and infrastructure changes without cloud credentials."""

import json
import shlex

from config import build_release_manifests, build_terraform_sizing_variables


def write_release_plan(target, recommendation, output_directory, recommendation_path):
    release_manifests = build_release_manifests(target, recommendation)
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "applications.json").write_text(
        json.dumps({"apiVersion": "v1", "kind": "List", "items": release_manifests}, indent=2)
        + "\n"
    )
    terraform_sizing_variables = build_terraform_sizing_variables(target, recommendation)
    (output_directory / "sizing.tfvars.json").unlink(missing_ok=True)
    for project in ("cluster", "applications/idea-board"):
        sizing_file_path = output_directory / "terraform" / project / "sizing.tfvars.json"
        if terraform_sizing_variables is None:
            sizing_file_path.unlink(missing_ok=True)
        else:
            sizing_file_path.parent.mkdir(parents=True, exist_ok=True)
            sizing_file_path.write_text(
                json.dumps(terraform_sizing_variables[project], indent=2) + "\n"
            )
    plan_sections = [
        f"# Release plan: {target.namespace}",
        f"Cloud: {target.cloud}. Image: `{target.image_tag}`. Charts: `{target.revision}`.",
        recommendation["reason"],
        "## Application changes",
    ]
    resource_table_rows = [
        "| Service | Replicas | CPU request | Memory request | Memory limit |",
        "| --- | --- | --- | --- | --- |",
    ]
    for service in ("backend", "frontend"):
        service_resources = recommendation[service]
        resource_table_rows.append(
            f"| {service} | {service_resources['replicas']} | "
            f"{service_resources['cpu_millicores']}m | "
            f"{service_resources['memory_request_mib']}Mi | "
            f"{service_resources['memory_limit_mib']}Mi |"
        )
    plan_sections += ["\n".join(resource_table_rows), "## Execution order", ""]
    plan_sections += [
        f"{index}. {step['action']}: {step['reason']}"
        for index, step in enumerate(recommendation["steps"], 1)
    ]
    release_command_arguments = [
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
        release_command_arguments += ["--pr", str(target.pr)]
    plan_sections += [
        "",
        "After reviewing sizing and the target context, run from the repository root:",
        "",
        "```bash",
        shlex.join(release_command_arguments),
        "```",
    ]
    if recommendation["infrastructure"]:
        plan_sections += [
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
            sizing_file_path = output_directory / "terraform" / project / "sizing.tfvars.json"
            plan_sections += [
                "```bash",
                "terragrunt run "
                f"--working-dir infra/terraform/{target.cloud}/"
                f"{target.environment}/YOUR_REGION/{project} -- plan "
                f"{shlex.quote('-var-file=' + str(sizing_file_path.resolve()))} "
                "-out=project.tfplan",
                "```",
            ]
        plan_sections += [
            "Review and apply each project separately. The proposals do not replace network, "
            "identity, or database protection settings."
        ]
    (output_directory / "plan.md").write_text("\n\n".join(plan_sections) + "\n")
