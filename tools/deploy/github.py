"""Read release provenance and PR state without executing pull-request content."""

import json
import os
import subprocess


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def check_release(repository, image_tag, environment, pr=0):
    if environment == "preview":
        pull = api(f"repos/{repository}/pulls/{pr}")
        if (
            pull["state"] != "open"
            or pull["head"]["sha"] != image_tag
            or pull["head"]["repo"]["full_name"] != repository
        ):
            raise ValueError("preview requires the current head of an open, same-repository PR")
    runs = api(
        f"repos/{repository}/actions/workflows/ci.yml/runs?head_sha={image_tag}&status=success&per_page=100"
    )
    if not any(run["conclusion"] == "success" for run in runs["workflow_runs"]):
        raise ValueError("image commit has no successful CI run")


def preview_matrix(event, event_name, repository, cloud):
    if cloud not in {"aws", "gcp"}:
        return []  # Previews stay off until an operator configures PREVIEW_CLOUD.
    if event_name == "workflow_run":
        run = event["workflow_run"]
        if (
            run["conclusion"] != "success"
            or run["event"] != "pull_request"
            or run["head_repository"]["full_name"] != repository
        ):
            return []
        pulls = api(f"repos/{repository}/commits/{run['head_sha']}/pulls")
        return [
            {
                "pr": pull["number"],
                "cloud": cloud,
                "image_tag": run["head_sha"],
                "operation": "release",
            }
            for pull in pulls
            if pull["state"] == "open"
            and pull["head"]["sha"] == run["head_sha"]
            and pull["head"]["repo"]["full_name"] == repository
        ]
    pull = event["pull_request"]
    if (
        event_name == "pull_request_target"
        and event["action"] == "closed"
        and pull["head"]["repo"]["full_name"] == repository
    ):
        return [
            {
                "pr": pull["number"],
                "cloud": cloud,
                "image_tag": pull["head"]["sha"],
                "operation": "cleanup",
            }
        ]
    return []


if __name__ == "__main__":
    event = json.loads(open(os.environ["GITHUB_EVENT_PATH"]).read())
    matrix = preview_matrix(
        event,
        os.environ["GITHUB_EVENT_NAME"],
        os.environ["GITHUB_REPOSITORY"],
        os.environ.get("PREVIEW_CLOUD", ""),
    )
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write("matrix=" + json.dumps({"include": matrix}) + "\n")
        output.write("enabled=" + str(bool(matrix)).lower() + "\n")
