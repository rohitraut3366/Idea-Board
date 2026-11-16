"""Render reusable secret configuration without application-specific fields."""

import json
import subprocess
from pathlib import Path

import pytest

CHART = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("override", ["", "custom-secrets"])
def test_extracts_multiple_secrets_with_configured_target(override):
    values = {
        "fullnameOverride": override,
        "secretName": "worker-config",
        "provider": {"gcpsm": {"projectID": "test-project"}},
        "dataFrom": [{"extract": {"key": key}} for key in ("database", "worker-token")],
    }
    output = subprocess.run(
        ["helm", "template", "worker", str(CHART), "-f", "-"],
        input=json.dumps(values),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "name: worker-config" in output
    assert f"name: {override or 'worker-secrets'}" in output
    assert "key: database" in output and "key: worker-token" in output
    assert "projectID: test-project" in output
    assert "kind: SecretStore" in output and "kind: ExternalSecret" in output
    assert "DATABASE_URL" not in output


def test_requires_secret_source_configuration():
    result = subprocess.run(
        ["helm", "template", "worker", str(CHART), "--set", "secretName=worker-config"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "provider and dataFrom are required" in result.stderr
