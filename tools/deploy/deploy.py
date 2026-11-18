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
    parent_application,
    prompt,
    validate_recommendation,
)
from database import ensure_database_secret
from root import cloud_root


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

    argo_project, backend_application, frontend_application = manifests(target, recommendation)
    service_applications = [backend_application, frontend_application]
    cloud_root_application = None
    if target.uses_cloud_root:
        existing_cloud_root_application = cluster.get("application", "idea-board", "argocd")
        if not existing_cloud_root_application:
            raise ValueError("install the cloud root through cluster-core-services first")
        cloud_root_application = cloud_root(target, [], existing_cloud_root_application)
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
        if not target.uses_cloud_root:
            ensure_database_secret(cluster)
        release_manifests = [argo_project, *service_applications]
        if target.cloud == "kind":
            release_manifests = [argo_project, parent_application(target, service_applications)]
        elif target.uses_cloud_root:
            release_manifests = [cloud_root(target, service_applications, cloud_root_application)]
        Path("applications.json").write_text(
            json.dumps({"apiVersion": "v1", "kind": "List", "items": release_manifests}, indent=2)
            + "\n"
        )
        checkpoint(cluster, target, service_applications)
        if not target.uses_cloud_root:
            cluster.apply(argo_project)
        if target.cloud == "kind":
            # Keep the serving frontend while the new backend runs its migration and checks.
            existing_frontend_application = cluster.get(
                "application", f"{target.namespace}-frontend", "argocd"
            )
            backend_phase_applications = [backend_application] + (
                [existing_frontend_application] if existing_frontend_application else []
            )
            phase = "backend"
            environment_parent_application = parent_application(target, backend_phase_applications)
            cluster.apply(environment_parent_application)
            cluster.wait([environment_parent_application])
            cluster.wait([backend_application])
            phase = "frontend"
            environment_parent_application = parent_application(target, service_applications)
            cluster.apply(environment_parent_application)
            cluster.wait([environment_parent_application])
            cluster.wait([frontend_application])
        elif target.uses_cloud_root:
            for application in service_applications:
                phase = chart_source(application)["helm"]["releaseName"]
                cloud_root_application = cloud_root(target, [application], cloud_root_application)
                cluster.apply(cloud_root_application)
                cluster.wait([cloud_root_application])
                cluster.wait([application])
        else:
            for application in service_applications:
                phase = chart_source(application)["helm"]["releaseName"]
                cluster.apply(application)
                cluster.wait([application])
        phase = "http"
        cluster.verify()
        phase = "public_http" if target.cloud != "kind" else "http"
        url = cluster.public_url() if target.cloud != "kind" else None
        record_healthy(cluster, service_applications)
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
    if target.cloud == "kind":
        cluster.run(
            "--namespace",
            "argocd",
            "delete",
            "application",
            target.namespace,
            "--ignore-not-found",
            "--wait=true",
            "--timeout=10m",
        )
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
