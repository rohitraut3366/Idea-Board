"""Check bundled PostgreSQL wiring and migration ordering."""

import subprocess
from pathlib import Path

CHART = Path(__file__).resolve().parents[1]


def render(*arguments):
    return subprocess.run(
        ["helm", "template", "backend", str(CHART), "-n", "chart-check", *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def job(output):
    return next(document for document in output.split("---") if "kind: Job\n" in document)


def test_external_database_keeps_presync_migration_and_existing_secret():
    output = render("--set", "databaseSecretName=managed-database")
    assert "kind: PersistentVolumeClaim" not in output
    assert "kind: Secret\n" not in output
    assert 'name: "managed-database"' in output
    assert "argocd.argoproj.io/hook: PreSync" in job(output)
    assert "helm.sh/hook: pre-install,pre-upgrade" in job(output)


def test_kind_bundles_postgres_before_migration_and_backend():
    output = render("-f", str(CHART / "values-kind.yaml"))
    assert "kind: PersistentVolumeClaim" in output
    assert "postgres.chart-check.svc.cluster.local:5432/idea_board" in output
    assert 'value: "idea_board_local"' in output
    assert 'name: "idea-board-database"' in output
    assert "argocd.argoproj.io/hook: Sync\n" in job(output)
    assert 'argocd.argoproj.io/sync-wave: "-1"' in job(output)
    assert "helm.sh/hook:" not in job(output)
    for document in output.split("---"):
        if "charts/postgres/" in document or "kind: Secret\n" in document:
            assert 'argocd.argoproj.io/sync-wave: "-2"' in document
    assert "helm.sh/resource-policy: keep" in output
    assert "argocd.argoproj.io/sync-options: Prune=false" in output


def test_bundled_database_connection_follows_overrides():
    output = render(
        "--set",
        "postgres.enabled=true",
        "--set",
        "postgres.password=local-password",
        "--set",
        "postgres.username=local-user",
        "--set",
        "postgres.database=local_db",
        "--set",
        "postgres.fullnameOverride=custom-postgres",
    )
    assert (
        "local-user:local-password@custom-postgres.chart-check.svc.cluster.local:5432/local_db"
        in output
    )
    assert 'name: "backend-database"' in output
    assert 'value: "local_db"' in output and 'value: "local-user"' in output


def test_new_image_gets_a_new_bundled_migration_job():
    first = render("-f", str(CHART / "values-kind.yaml"), "--set", "image.tag=first")
    second = render("-f", str(CHART / "values-kind.yaml"), "--set", "image.tag=second")
    first_name = next(line for line in job(first).splitlines() if line.startswith("  name:"))
    second_name = next(line for line in job(second).splitlines() if line.startswith("  name:"))
    assert first_name != second_name
