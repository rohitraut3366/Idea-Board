"""Exercise staging, preview redeployment, and cleanup on an existing test kind cluster."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cluster import Cluster  # noqa: E402
from config import Target, manifests  # noqa: E402
from deploy import cleanup, release  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
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
        for document in manifests(target, {"profile": "small", "reason": "preflight"}):
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

    def psql(statement):
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
            database,
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
        recommendation = {"profile": "small", "reason": "Isolated local release check"}
        with tempfile.TemporaryDirectory(prefix="idea-board-release-check-") as directory:
            os.chdir(directory)
            release(staging_cluster, staging, recommendation)
            release(preview_cluster, preview, recommendation)
            first_url = preview_cluster.database_url()
            release(preview_cluster, preview, recommendation)
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
            print("Passed staging, preview release/redeployment, HTTP checks, and cleanup.")
    finally:
        # These namespaces, database names, and role were checked absent before this test.
        for target in (preview, staging):
            for document in reversed(manifests(target, {"profile": "small", "reason": "cleanup"})):
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
