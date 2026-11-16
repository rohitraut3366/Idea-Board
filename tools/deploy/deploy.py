"""Run with `uv run python deploy.py --help` from tools/deploy."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from cluster import Cluster
from config import (
    Target,
    chart_source,
    deployment_manifests,
    manifests,
    prompt,
    validate_recommendation,
)
from database import ensure_database_secret
from root import application_key, environment_root, existing_root, shared_root


def cleanup_closed_preview(cluster, target):
    if target.environment != "preview" or target.cloud == "kind":
        return False
    from config import REPOSITORY
    from github import api

    repository = REPOSITORY.removeprefix("https://github.com/").removesuffix(".git")
    if api(f"repos/{repository}/pulls/{target.pr}")["state"] == "closed":
        cleanup(cluster, target)
        return True
    return False


def release(cluster, target, recommendation):
    from diagnosis import collect
    from rollback import checkpoint, record_healthy, state

    documents = manifests(target, recommendation)
    root = existing_root(cluster, target)
    outcome = "failed"
    phase = "database"
    rollback_available = False
    try:
        if target.cloud == "aws":
            phase = "ingress_controller"
            cluster.run(
                "--namespace",
                "kube-system",
                "rollout",
                "status",
                "deployment/aws-load-balancer-controller",
                "--timeout=3m",
            )
            phase = "database"
        cluster.ensure_namespace(target.environment)
        rollback_available = bool(state(cluster)["healthy"])
        if not target.uses_managed_database:
            ensure_database_secret(cluster)
        release_documents = [shared_root(target, documents[1:], root)]
        if not target.uses_managed_database:
            release_documents.insert(0, documents[0])
        Path("applications.json").write_text(
            json.dumps({"apiVersion": "v1", "kind": "List", "items": release_documents}, indent=2)
            + "\n"
        )
        checkpoint(cluster, target, documents[1:])
        if not target.uses_managed_database:
            cluster.apply(documents[0])
        for application in documents[1:]:
            phase = chart_source(application)["helm"]["releaseName"]
            # Refresh before each update to retain changes made by other environments.
            root = shared_root(target, [application], environment_root(cluster, target))
            cluster.apply(root)
            cluster.wait([root])
            cluster.wait([application])
        phase = "http"
        cluster.verify()
        phase = "public_http" if target.cloud != "kind" else "http"
        url = cluster.public_url() if target.cloud != "kind" else None
        record_healthy(cluster, documents[1:])
        outcome = "healthy"
    finally:
        # Collect facts even when credentials or the API are unavailable; no raw logs are saved.
        Path("deployment-diagnostics.json").write_text(
            json.dumps(collect(cluster, outcome, rollback_available, phase), indent=2) + "\n"
        )
        closed = cleanup_closed_preview(cluster, target)
    if closed:
        raise RuntimeError("PR closed during release; preview resources were cleaned up")
    result = {
        "namespace": target.namespace,
        "image_tag": target.image_tag,
        "chart_revision": target.revision,
        "resources": {service: recommendation[service] for service in ("backend", "frontend")},
        "reason": recommendation["reason"],
        "status": "healthy",
        "url": url,
    }
    Path("deployment-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as output:
            output.write(f"\nRelease: `{target.image_tag}`\n\nNamespace: `{target.namespace}`\n")
            if url:
                output.write(f"\nApplication: {url}\n")


def cleanup(cluster, target):
    if target.environment != "preview":
        raise ValueError("automated cleanup is restricted to previews")
    namespace = cluster.get("namespace", target.namespace)
    if namespace:
        cluster.ensure_namespace("preview")
    root = environment_root(cluster, target)
    children = root["spec"]["source"]["helm"]["valuesObject"].setdefault("applications", {})
    for service in ("frontend", "backend"):
        children.pop(application_key(target, service), None)
    cluster.apply(root)
    cluster.wait([root])
    # Delete the Ingress owner first so cloud backends can detach before Service cleanup.
    for service in ("frontend", "backend"):
        cluster.run(
            "--namespace",
            "argocd",
            "delete",
            "application",
            f"{target.namespace}-{service}",
            "--ignore-not-found",
            "--wait=true",
            "--timeout=10m",
        )
    if namespace:
        cluster.run("delete", "namespace", target.namespace, "--wait=true", "--timeout=5m")
    cluster.run(
        "--namespace",
        "argocd",
        "delete",
        "appproject",
        target.namespace,
        "--ignore-not-found",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("prompt", "render", "prepare", "release", "cleanup", "rollback")
    )
    parser.add_argument("--cloud", choices=("kind", "aws", "gcp"), required=True)
    parser.add_argument(
        "--environment", choices=("preview", "staging", "production"), required=True
    )
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--pr", type=int, default=0)
    parser.add_argument("--request", default=os.environ.get("DEPLOY_REQUEST", ""))
    parser.add_argument("--recommendation", type=Path)
    parser.add_argument("--context")
    parser.add_argument("--output-dir", type=Path, default=Path("release-plan"))
    parser.add_argument("--schema-compatible", action="store_true")
    arguments = parser.parse_args()
    target = Target(
        arguments.cloud,
        arguments.environment,
        arguments.image_tag,
        arguments.revision,
        arguments.pr or None,
    )
    if arguments.command == "prompt":
        print(prompt(target, arguments.request))
        return
    if arguments.command == "rollback":
        from rollback import rollback

        result = rollback(
            Cluster(arguments.context, target.namespace), target, arguments.schema_compatible
        )
        Path("deployment-result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return
    if arguments.command == "cleanup":
        cleanup(Cluster(arguments.context, target.namespace), target)
        return
    if not arguments.recommendation:
        parser.error("--recommendation is required for render, prepare, and release")
    recommendation = json.loads(arguments.recommendation.read_text())
    validate_recommendation(recommendation, target.environment, target.cloud)
    if arguments.command == "prepare":
        from planning import prepare

        prepare(target, recommendation, arguments.output_dir, arguments.recommendation)
    elif arguments.command == "render":
        print(
            json.dumps(
                {
                    "apiVersion": "v1",
                    "kind": "List",
                    "items": deployment_manifests(target, recommendation),
                },
                indent=2,
            )
        )
    else:
        release(Cluster(arguments.context, target.namespace), target, recommendation)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, TimeoutError, KeyError, subprocess.SubprocessError) as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        sys.exit(1)
