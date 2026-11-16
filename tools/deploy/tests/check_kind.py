"""Exercise staging, preview redeployment, and cleanup on an existing test kind cluster."""

import argparse
import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recommendations import recommendation  # noqa: E402

from cluster import Cluster  # noqa: E402
from config import REPOSITORY, Target, manifests  # noqa: E402
from database import ensure_database_secret  # noqa: E402
from deploy import cleanup, release  # noqa: E402
from diagnosis import collect  # noqa: E402
from rollback import checkpoint, rollback, state  # noqa: E402
from root import existing_root, shared_root  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--evidence-output", type=Path)
    args = parser.parse_args()
    evidence_output = args.evidence_output.resolve() if args.evidence_output else None
    if not args.context.startswith("kind-"):
        raise ValueError("this check is restricted to an explicit kind context")
    staging = Target("kind", "staging", args.image_tag, args.revision)
    preview = Target("kind", "preview", args.image_tag, args.revision, 999999999)
    source = Cluster(args.context, "idea-board")
    staging_cluster = Cluster(args.context, staging.namespace)
    preview_cluster = Cluster(args.context, preview.namespace)
    for target in (staging, preview):
        if source.get("namespace", target.namespace):
            raise ValueError(f"Refusing to use existing namespace {target.namespace}")
        if source.get("application", target.namespace, "argocd"):
            raise ValueError("release-check parent Application already exists")
        for document in manifests(target, recommendation()):
            if source.get(document["kind"].lower(), document["metadata"]["name"], "argocd"):
                raise ValueError("release-check Argo resources already exist")

    def psql(cluster, statement):
        return cluster.run(
            "--namespace",
            cluster.namespace,
            "exec",
            "deployment/postgres",
            "--",
            "psql",
            "-U",
            "idea_board",
            "-d",
            "idea_board",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            statement,
        )

    try:
        proposal = recommendation()
        with tempfile.TemporaryDirectory(prefix="idea-board-release-check-") as directory:
            os.chdir(directory)
            # Start with the former environment-parent layout to exercise adoption.
            staging_cluster.ensure_namespace("staging")
            ensure_database_secret(staging_cluster)
            project, *children = manifests(staging, proposal)
            project["spec"]["destinations"].append(
                {"server": "https://kubernetes.default.svc", "namespace": "argocd"}
            )
            project["spec"]["namespaceResourceWhitelist"].append(
                {"group": "argoproj.io", "kind": "Application"}
            )
            staging_cluster.apply(project)
            legacy_parent = {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Application",
                "metadata": {
                    "name": staging.namespace,
                    "namespace": "argocd",
                    "finalizers": ["resources-finalizer.argocd.argoproj.io"],
                },
                "spec": {
                    "project": staging.namespace,
                    "source": {
                        "repoURL": REPOSITORY,
                        "targetRevision": args.revision,
                        "path": "gitops/applications",
                        "helm": {
                            "valuesObject": {
                                "project": staging.namespace,
                                "namespace": staging.namespace,
                                "namePrefix": staging.namespace + "-",
                                "applications": {
                                    child["spec"]["source"]["helm"]["releaseName"]: {
                                        "enabled": True,
                                        "source": child["spec"]["source"],
                                        "syncPolicy": child["spec"]["syncPolicy"],
                                    }
                                    for child in children
                                },
                            }
                        },
                    },
                    "destination": {
                        "server": "https://kubernetes.default.svc",
                        "namespace": "argocd",
                    },
                    "syncPolicy": {
                        "automated": {"prune": True, "selfHeal": True},
                        "syncOptions": ["ServerSideApply=true"],
                    },
                },
            }
            staging_cluster.apply(legacy_parent)
            staging_cluster.wait([legacy_parent])
            staging_cluster.wait(children)
            original_credentials = staging_cluster.database_url()
            psql(
                staging_cluster,
                "CREATE TABLE adoption_canary (content text); "
                "INSERT INTO adoption_canary VALUES ('keep while adopting')",
            )
            release(staging_cluster, staging, proposal)
            assert not source.get("application", staging.namespace, "argocd")
            assert staging_cluster.database_url() == original_credentials
            assert psql(staging_cluster, "SELECT content FROM adoption_canary").strip() == (
                "keep while adopting"
            )
            release(preview_cluster, preview, proposal)
            roots = json.loads(
                source.run("--namespace", "argocd", "get", "applications", "-o", "json")
            )
            assert [
                app["metadata"]["name"]
                for app in roots["items"]
                if app["spec"].get("source", {}).get("path") == "gitops/applications"
            ] == ["idea-board"]
            assert staging_cluster.database_url() != preview_cluster.database_url()
            psql(
                preview_cluster,
                "CREATE TABLE preview_canary (content text); "
                "INSERT INTO preview_canary VALUES ('keep across redeploy')",
            )
            first_url = preview_cluster.database_url()
            release(preview_cluster, preview, proposal)
            assert preview_cluster.database_url() == first_url, (
                "redeploy rotated preview credentials"
            )
            assert psql(preview_cluster, "SELECT content FROM preview_canary").strip() == (
                "keep across redeploy"
            )
            assert psql(staging_cluster, "SELECT to_regclass('preview_canary')").strip() == ""
            assert preview_cluster.get("persistentvolumeclaim", "postgres-data", preview.namespace)
            cleanup(preview_cluster, preview)
            assert not source.get("namespace", preview.namespace)
            assert staging_cluster.get("persistentvolumeclaim", "postgres-data", staging.namespace)
            staging_cluster.verify()
            # Fail a frontend rollout with an unpublished image, then restore Argo desired state.
            # The checkpoint retains the last release that passed all HTTP checks.
            psql(
                staging_cluster,
                "CREATE TABLE rollback_canary (content text); "
                "INSERT INTO rollback_canary VALUES ('preserve through rollback')",
            )
            schema_version = psql(staging_cluster, "SELECT version_num FROM alembic_version")
            failed = Target("kind", "staging", "f" * 40, args.revision)
            bad_applications = deepcopy(state(staging_cluster)["healthy"])
            bad_applications[1]["spec"]["source"]["helm"]["valuesObject"]["image"]["tag"] = (
                failed.image_tag
            )
            # Change the backend request too, so rollback must reconcile its old values.
            bad_applications[0]["spec"]["source"]["helm"]["valuesObject"]["resources"]["requests"][
                "cpu"
            ] = "125m"
            checkpoint(staging_cluster, failed, bad_applications)
            failed_parent = shared_root(
                failed, bad_applications, existing_root(staging_cluster, failed)
            )
            staging_cluster.apply(failed_parent)
            staging_cluster.wait([failed_parent])
            staging_cluster.wait([bad_applications[0]])
            try:
                staging_cluster.wait([bad_applications[1]], timeout=45)
            except TimeoutError:
                pass
            else:
                raise AssertionError("unpublished image unexpectedly passed rollout health checks")
            evidence = collect(staging_cluster, "failed", True)
            assert any(
                container.get("reason") in {"ImagePullBackOff", "ErrImagePull"}
                for entry in evidence["evidence"]
                if entry["kind"] == "pod"
                for container in entry["facts"]["containers"]
            ), "failure evidence did not capture the image pull error"
            if evidence_output:
                evidence_output.write_text(json.dumps(evidence, indent=2) + "\n")
            assert (
                rollback(staging_cluster, failed, schema_compatible=True)["status"] == "rolled_back"
            )
            restored_backend = staging_cluster.get(
                "application", f"{staging.namespace}-backend", "argocd"
            )
            operation = restored_backend["status"]["operationState"]
            assert operation["phase"] == "Succeeded"
            assert operation["operation"]["sync"]["syncStrategy"] == {"apply": {}}
            assert restored_backend["spec"]["syncPolicy"]["automated"]["enabled"] is False
            sync_resources = operation["syncResult"].get("resources", [])
            assert not any(
                resource.get("kind") == "Job" and "migrate" in resource.get("name", "")
                for resource in sync_resources
            ), "rollback ran a migration hook"
            assert state(staging_cluster)["attempt"] is None
            assert (
                psql(staging_cluster, "SELECT content FROM rollback_canary").strip()
                == "preserve through rollback"
            )
            assert (
                psql(staging_cluster, "SELECT version_num FROM alembic_version") == schema_version
            )
            print(
                "Passed staging, preview persistence/cleanup, image failure detection, "
                "Argo rollback, and HTTP checks."
            )
    finally:
        # Only these environments were checked absent and created by this test.
        for target in (preview, staging):
            root = existing_root(source, target)
            entries = root["spec"]["source"]["helm"]["valuesObject"].get("applications", {})
            for service in ("backend", "frontend"):
                entries.pop(f"{target.namespace}-{service}", None)
            # Root auto-sync remains enabled after rollback; only restored children pause.
            source.apply(root)
            source.wait([root])
            for document in reversed(manifests(target, recommendation())):
                kind = document["kind"].lower()
                source.run(
                    "--namespace",
                    "argocd",
                    "delete",
                    kind,
                    document["metadata"]["name"],
                    "--ignore-not-found",
                    "--wait=true",
                    "--timeout=5m",
                )
            source.run(
                "delete",
                "namespace",
                target.namespace,
                "--ignore-not-found",
                "--wait=true",
                "--timeout=3m",
            )
        print(json.dumps({"cleanup": "complete", "context": args.context}))


if __name__ == "__main__":
    main()
