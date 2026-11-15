"""Check the cluster services app-of-apps on an existing kind cluster."""

import argparse
import json
import subprocess
import time
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
ARGOCD_MODULE = REPOSITORY / "infra/terraform/modules/argocd"


def run(*arguments):
    return subprocess.run(arguments, check=True, text=True, capture_output=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    if not args.context.startswith("kind-"):
        raise ValueError("this check requires an explicit kind context")
    kubectl = ("kubectl", "--context", args.context)
    run(
        "helm",
        "--kube-context",
        args.context,
        "upgrade",
        "--install",
        "cluster-core-services",
        str(ARGOCD_MODULE / "bootstrap"),
        "--namespace",
        "argocd",
        "--set-string",
        f"targetRevision={args.revision}",
        "--wait",
        "--timeout",
        "2m",
    )
    deadline = time.monotonic() + 600
    statuses = {}
    while time.monotonic() < deadline:
        applications = json.loads(
            run(*kubectl, "--namespace", "argocd", "get", "applications", "-o", "json")
        )["items"]
        expected = [
            app
            for app in applications
            if app["metadata"]["name"] in {"cluster-core-services", "external-secrets"}
        ]
        statuses = {app["metadata"]["name"]: app.get("status", {}) for app in expected}
        ready = len(expected) == 2
        for app in expected:
            source = app["spec"]["source"]
            status = app.get("status", {})
            ready = ready and (
                source["targetRevision"] == args.revision
                and status.get("sync", {}).get("comparedTo", {}).get("source") == source
                and status.get("sync", {}).get("status") == "Synced"
                and status.get("health", {}).get("status") == "Healthy"
                and status.get("operationState", {}).get("phase") == "Succeeded"
            )
        if ready:
            break
        time.sleep(5)
    else:
        raise TimeoutError(f"Cluster services did not become Synced and Healthy: {statuses}")
    run(
        *kubectl,
        "wait",
        "--for=condition=Established",
        "crd/externalsecrets.external-secrets.io",
        "crd/secretstores.external-secrets.io",
        "--timeout=1m",
    )
    print("Passed: root Application and External Secrets Operator are Synced and Healthy.")


if __name__ == "__main__":
    main()
