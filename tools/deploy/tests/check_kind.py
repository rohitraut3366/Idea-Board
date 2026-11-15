"""Exercise staging, preview redeployment, and cleanup on an existing test kind cluster."""

import argparse
import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recommendations import recommendation  # noqa: E402

from cluster import Cluster  # noqa: E402
from config import Target, manifests  # noqa: E402
from deploy import cleanup, release  # noqa: E402
from diagnosis import collect  # noqa: E402
from rollback import checkpoint, rollback, state  # noqa: E402


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
        for document in manifests(target, recommendation()):
            if source.get(document["kind"].lower(), document["metadata"]["name"], "argocd"):
                raise ValueError("release-check Argo resources already exist")
    original = source.database_url()
    if not original:
        raise ValueError("idea-board requires the chart test PostgreSQL database and Secret")
    parsed = urlsplit(original)
    if not parsed.username or not parsed.password:
        raise ValueError("the test database URL requires a username and password")
    username = unquote(parsed.username)
    database = unquote(parsed.path[1:])

    def psql(statement, database_name=database):
        return source.run(
            "--namespace",
            "idea-board",
            "exec",
            "deployment/postgres",
            "--",
            "psql",
            "-U",
            username,
            "-d",
            database_name,
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            statement,
        )

    existing = psql(
        "SELECT datname FROM pg_database WHERE datname IN "
        "('idea_board_release_check', 'idea_board_pr_999999999')"
    )
    existing_role = psql("SELECT rolname FROM pg_roles WHERE rolname = 'idea_board_pr_999999999'")
    if existing.strip() or existing_role.strip():
        raise ValueError("local release-check database or role already exists")
    psql('CREATE DATABASE "idea_board_release_check"')
    stage_url = urlunsplit(
        (
            parsed.scheme,
            f"{parsed.username}:{parsed.password}@postgres.idea-board.svc.cluster.local:5432",
            "/idea_board_release_check",
            parsed.query,
            "",
        )
    )
    try:
        os.environ["IDEA_BOARD_DATABASE_URL"] = stage_url
        proposal = recommendation()
        with tempfile.TemporaryDirectory(prefix="idea-board-release-check-") as directory:
            os.chdir(directory)
            release(staging_cluster, staging, proposal)
            release(preview_cluster, preview, proposal)
            first_url = preview_cluster.database_url()
            release(preview_cluster, preview, proposal)
            assert preview_cluster.database_url() == first_url, (
                "redeploy rotated preview credentials"
            )
            cleanup(preview_cluster, preview)
            assert not source.get("namespace", preview.namespace)
            assert not psql(
                "SELECT datname FROM pg_database WHERE datname = 'idea_board_pr_999999999'"
            ).strip()
            assert not psql(
                "SELECT rolname FROM pg_roles WHERE rolname = 'idea_board_pr_999999999'"
            ).strip()
            # Fail a frontend rollout with an unpublished image, then restore Argo desired state.
            # The checkpoint retains the last release that passed all HTTP checks.
            psql(
                "CREATE TABLE rollback_canary (content text); "
                "INSERT INTO rollback_canary VALUES ('preserve through rollback')",
                "idea_board_release_check",
            )
            schema_version = psql(
                "SELECT version_num FROM alembic_version", "idea_board_release_check"
            )
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
            staging_cluster.apply(bad_applications[0])
            staging_cluster.wait([bad_applications[0]])
            staging_cluster.apply(bad_applications[1])
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
            assert not any(resource.get("hookType") == "PreSync" for resource in sync_resources), (
                "rollback ran a migration hook"
            )
            assert state(staging_cluster)["attempt"] is None
            assert (
                psql("SELECT content FROM rollback_canary", "idea_board_release_check").strip()
                == "preserve through rollback"
            )
            assert (
                psql("SELECT version_num FROM alembic_version", "idea_board_release_check")
                == schema_version
            )
            print(
                "Passed staging, preview persistence/cleanup, image failure detection, "
                "Argo rollback, and HTTP checks."
            )
    finally:
        # These namespaces, database names, and role were checked absent before this test.
        for target in (preview, staging):
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
        psql('DROP DATABASE IF EXISTS "idea_board_pr_999999999" WITH (FORCE)')
        psql('DROP ROLE IF EXISTS "idea_board_pr_999999999"')
        psql('DROP DATABASE "idea_board_release_check" WITH (FORCE)')
        print(json.dumps({"cleanup": "complete", "context": args.context}))


if __name__ == "__main__":
    main()
