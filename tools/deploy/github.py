"""Read release provenance and PR state without executing pull-request content."""

import json
import os
import subprocess


def get_github_json(api_path):
    return json.loads(subprocess.check_output(["gh", "api", api_path], text=True))


def validate_release_provenance(repository, image_tag, environment, pr=0):
    if environment == "preview":
        pull_request = get_github_json(f"repos/{repository}/pulls/{pr}")
        if (
            pull_request["state"] != "open"
            or pull_request["head"]["sha"] != image_tag
            or pull_request["head"]["repo"]["full_name"] != repository
        ):
            raise ValueError("preview requires the current head of an open, same-repository PR")
    workflow_runs_response = get_github_json(
        f"repos/{repository}/actions/workflows/ci.yml/runs?head_sha={image_tag}&status=success&per_page=100"
    )
    if not any(
        workflow_run["conclusion"] == "success"
        for workflow_run in workflow_runs_response["workflow_runs"]
    ):
        raise ValueError("image commit has no successful CI run")


def build_preview_job_matrix(event, event_name, repository, cloud):
    if cloud not in {"aws", "gcp"}:
        return []  # Previews stay off until an operator configures PREVIEW_CLOUD.
    if event_name == "workflow_run":
        workflow_run = event["workflow_run"]
        if (
            workflow_run["conclusion"] != "success"
            or workflow_run["event"] != "pull_request"
            or workflow_run["head_repository"]["full_name"] != repository
        ):
            return []
        pull_requests = get_github_json(
            f"repos/{repository}/commits/{workflow_run['head_sha']}/pulls"
        )
        return [
            {
                "pr": pull_request["number"],
                "cloud": cloud,
                "image_tag": workflow_run["head_sha"],
                "operation": "release",
            }
            for pull_request in pull_requests
            if pull_request["state"] == "open"
            and pull_request["head"]["sha"] == workflow_run["head_sha"]
            and pull_request["head"]["repo"]["full_name"] == repository
        ]
    pull_request = event["pull_request"]
    if (
        event_name == "pull_request_target"
        and event["action"] == "closed"
        and pull_request["head"]["repo"]["full_name"] == repository
    ):
        return [
            {
                "pr": pull_request["number"],
                "cloud": cloud,
                "image_tag": pull_request["head"]["sha"],
                "operation": "cleanup",
            }
        ]
    return []


if __name__ == "__main__":
    event = json.loads(open(os.environ["GITHUB_EVENT_PATH"]).read())
    matrix = build_preview_job_matrix(
        event,
        os.environ["GITHUB_EVENT_NAME"],
        os.environ["GITHUB_REPOSITORY"],
        os.environ.get("PREVIEW_CLOUD", ""),
    )
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write("matrix=" + json.dumps({"include": matrix}) + "\n")
        output.write("enabled=" + str(bool(matrix)).lower() + "\n")
