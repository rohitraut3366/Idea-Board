"""Bootstrap and verify the local root and its child Applications in kind."""

import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*arguments, data=None):
    return subprocess.run(
        arguments,
        input=data,
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--image-tag", required=True)
    args = parser.parse_args()
    if not args.context.startswith("kind-"):
        raise ValueError("an explicit kind context is required")
    kubectl = ("kubectl", "--context", args.context)
    manifests = run("kubectl", "kustomize", str(ROOT / "gitops/kind"))
    documents = json.loads(
        run(
            *kubectl,
            "create",
            "--dry-run=client",
            "--validate=false",
            "-f",
            "-",
            "-o",
            "json",
            data=manifests,
        )
    )
    for document in documents["items"]:
        if document["kind"] == "Application":
            document["spec"]["source"]["targetRevision"] = args.revision
            document["spec"]["source"]["helm"]["valuesObject"] = {
                "targetRevision": args.revision,
                "imageTag": args.image_tag,
            }
    run(
        *kubectl,
        "apply",
        "--server-side",
        "--field-manager=idea-board-local-bootstrap",
        "-f",
        "-",
        data=json.dumps(documents),
    )
    expected = {"local", "idea-board", "ingress-controller", "backend", "frontend"}
    deadline = time.monotonic() + 600
    statuses = {}
    while time.monotonic() < deadline:
        applications = json.loads(
            run(*kubectl, "-n", "argocd", "get", "applications", "-o", "json")
        )["items"]
        selected = [app for app in applications if app["metadata"]["name"] in expected]
        statuses = {
            app["metadata"]["name"]: {
                "sync": app.get("status", {}).get("sync", {}).get("status"),
                "health": app.get("status", {}).get("health", {}).get("status"),
            }
            for app in selected
        }
        if len(selected) == len(expected) and all(
            state == {"sync": "Synced", "health": "Healthy"} for state in statuses.values()
        ):
            break
        time.sleep(5)
    else:
        raise TimeoutError(f"Local Applications did not become ready: {statuses}")
    for app in selected:
        assert app["spec"]["source"]["targetRevision"] == args.revision
        assert app["status"]["sync"].get("comparedTo", {}).get("source") == app["spec"]["source"]
        if app["metadata"]["name"] != "local":
            expected_parent = (
                "idea-board" if app["metadata"]["name"] in {"backend", "frontend"} else "local"
            )
            tracking = (
                app["metadata"].get("annotations", {}).get("argocd.argoproj.io/tracking-id", "")
            )
            assert tracking.startswith(expected_parent + ":"), (
                "A child has the wrong parent tracking annotation"
            )
    secret_apis = run(*kubectl, "api-resources", "--api-group=external-secrets.io", "-o", "name")
    assert not secret_apis.strip(), "Local bootstrap installed External Secrets CRDs"
    assert not run(
        *kubectl,
        "-n",
        "argocd",
        "get",
        "application",
        "external-secrets",
        "--ignore-not-found",
        "-o",
        "name",
    ).strip()
    print(
        "Passed: local root, environment parent, ingress, frontend and backend are "
        "Synced and Healthy; External Secrets is disabled."
    )


if __name__ == "__main__":
    main()
