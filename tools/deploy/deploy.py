"""Run with `uv run python deploy.py --help` from tools/deploy."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from cluster import Cluster
from config import Target, manifests, prompt, validate_recommendation


def preview_database(cluster, target, delete=False):
    # psycopg and the staging owner credential are already available in the backend.
    # Run here rather than opening the private database to a hosted Actions runner.
    database_source = Path(__file__).with_name("database.py").read_text()
    if delete:
        operation = f'delete_preview(os.environ["IDEA_BOARD_DATABASE_URL"], {target.pr})'
    else:
        existing = cluster.database_url()
        operation = (
            f'print(json.dumps(prepare_preview(os.environ["IDEA_BOARD_DATABASE_URL"], '
            f"{target.pr}, {existing!r})))"
        )
    return cluster.run(
        "--namespace",
        "idea-board-staging",
        "exec",
        "-i",
        "deployment/backend",
        "--",
        "python",
        "-",
        data=database_source + "\n" + operation + "\n",
    )


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
    from database import managed_database_url

    documents = manifests(target, recommendation)
    try:
        cluster.ensure_namespace(target.environment)
        if target.environment == "preview":
            url = json.loads(preview_database(cluster, target))
        else:
            url = managed_database_url(target.cloud)
        cluster.set_database_url(url)
        documents[1]["spec"]["source"]["helm"]["valuesObject"]["databaseRevision"] = hashlib.sha256(
            url.encode()
        ).hexdigest()
        Path("applications.json").write_text(
            json.dumps({"apiVersion": "v1", "kind": "List", "items": documents}, indent=2) + "\n"
        )
        cluster.apply(documents[0])
        # The frontend resolves the backend Service at startup.
        for application in documents[1:]:
            cluster.apply(application)
            cluster.wait([application])
        cluster.verify()
        url = cluster.public_url() if target.cloud != "kind" else None
    except Exception:
        # Keep the failed release for inspection. Reverting the app cannot undo a migration.
        Path("deployment-diagnostics.json").write_text(json.dumps(cluster.diagnostics(), indent=2))
        raise
    finally:
        closed = cleanup_closed_preview(cluster, target)
    if closed:
        raise RuntimeError("PR closed during release; preview resources were cleaned up")
    result = {
        "namespace": target.namespace,
        "image_tag": target.image_tag,
        "chart_revision": target.revision,
        "profile": recommendation["profile"],
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
    for service in ("backend", "frontend"):
        cluster.run(
            "--namespace",
            "argocd",
            "delete",
            "application",
            f"{target.namespace}-{service}",
            "--ignore-not-found",
            "--wait=true",
            "--timeout=5m",
        )
    preview_database(cluster, target, delete=True)
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
    parser.add_argument("command", choices=("prompt", "render", "release", "cleanup"))
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
    if arguments.command == "cleanup":
        cleanup(Cluster(arguments.context, target.namespace), target)
        return
    if not arguments.recommendation:
        parser.error("--recommendation is required for render and release")
    recommendation = json.loads(arguments.recommendation.read_text())
    validate_recommendation(recommendation, target.environment)
    if arguments.command == "render":
        print(
            json.dumps(
                {"apiVersion": "v1", "kind": "List", "items": manifests(target, recommendation)},
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
