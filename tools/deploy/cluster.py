"""Argo CD deployment and verification with an explicit Kubernetes context."""

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from config import chart_source


class Cluster:
    def __init__(self, context, namespace):
        if not context:
            raise ValueError("an explicit Kubernetes context is required")
        self.context = context
        self.namespace = namespace

    def run(self, *arguments, data=None):
        result = subprocess.run(
            ["kubectl", "--context", self.context, *arguments],
            input=data if isinstance(data, str) else json.dumps(data) if data is not None else None,
            text=True,
            capture_output=True,
        )
        if result.returncode:
            # Do not include stdin: it may contain database credentials.
            raise RuntimeError(f"kubectl {arguments[0]} failed: {result.stderr.strip()}")
        return result.stdout

    def get(self, kind, name, namespace=None):
        arguments = ["get", kind, name, "--ignore-not-found", "-o", "json"]
        if namespace:
            arguments += ["--namespace", namespace]
        output = self.run(*arguments)
        return json.loads(output) if output.strip() else None

    def apply(self, document, force=False):
        self.run(
            "apply",
            "--server-side",
            "--field-manager=idea-board-deploy",
            *(["--force-conflicts"] if force else []),
            "-f",
            "-",
            data=document,
        )

    def ensure_namespace(self, environment):
        existing = self.get("namespace", self.namespace)
        labels = {
            "app.kubernetes.io/part-of": "idea-board",
            "idea-board/environment": environment,
        }
        if existing:
            actual = existing["metadata"].get("labels", {})
            if any(actual.get(key) != value for key, value in labels.items()):
                raise ValueError("namespace is not owned by this deployment tool")
        else:
            self.apply(
                {
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {"name": self.namespace, "labels": labels},
                }
            )

    def database_url(self):
        secret = self.get("secret", "idea-board-database", self.namespace)
        if not secret:
            return None
        return base64.b64decode(secret["data"]["DATABASE_URL"]).decode()

    def wait(self, applications, timeout=600):
        names = ", ".join(app["metadata"]["name"] for app in applications)
        print(f"Waiting up to {timeout}s for Applications: {names}", file=sys.stderr, flush=True)
        deadline = time.monotonic() + timeout
        pending = applications.copy()
        last_progress = {}
        poll_count = 0
        while pending and time.monotonic() < deadline:
            poll_count += 1
            for expected in pending.copy():
                name = expected["metadata"]["name"]
                current = self.get("application", name, "argocd")
                if not current:
                    if last_progress.get(name) != "not created" or poll_count % 10 == 0:
                        print(f"{name}: not created", file=sys.stderr, flush=True)
                        last_progress[name] = "not created"
                    continue
                status = current.get("status", {})
                source = chart_source(expected)
                compared = status.get("sync", {}).get("comparedTo", {}).get("source", {})
                same_source = (
                    all(
                        compared.get(key) == source[key]
                        for key in (
                            "repoURL",
                            "targetRevision",
                            "path",
                        )
                    )
                    and compared.get("helm", {}).get("valuesObject")
                    == source["helm"]["valuesObject"]
                )
                revision = status.get("sync", {}).get("revision")
                if "sources" in expected["spec"]:
                    same_source = (
                        status.get("sync", {}).get("comparedTo", {}).get("sources")
                        == expected["spec"]["sources"]
                    )
                    revisions = status.get("sync", {}).get("revisions", [])
                    revision = revisions[0] if revisions else None
                progress = (
                    f"sync={status.get('sync', {}).get('status', 'Unknown')}, "
                    f"health={status.get('health', {}).get('status', 'Unknown')}, "
                    f"operation={status.get('operationState', {}).get('phase', 'None')}, "
                    f"source_matches={same_source}, "
                    f"revision={revision}, expected_revision={source['targetRevision']}"
                )
                if last_progress.get(name) != progress or poll_count % 10 == 0:
                    print(f"{name}: {progress}", file=sys.stderr, flush=True)
                    last_progress[name] = progress
                if "operation" in expected:
                    operation_state = status.get("operationState", {})
                    if (
                        operation_state.get("operation", {}).get("info")
                        != expected["operation"]["info"]
                        or operation_state.get("phase") != "Succeeded"
                    ):
                        continue
                is_parent = source["path"] == "gitops/applications"
                if not same_source or (
                    (not is_parent or re.fullmatch(r"[0-9a-f]{40}", source["targetRevision"]))
                    and revision != source["targetRevision"]
                ):
                    continue
                if (
                    status.get("sync", {}).get("status") != "Synced"
                    or status.get("health", {}).get("status") != "Healthy"
                ):
                    continue
                if is_parent:
                    # Child readiness is checked separately, after the parent has reconciled.
                    if status.get("operationState", {}).get("phase") != "Succeeded":
                        continue
                    pending.remove(expected)
                    print(f"{name}: ready", file=sys.stderr, flush=True)
                    continue
                release = source["helm"]["releaseName"]
                deployment = self.get("deployment", release, self.namespace)
                if not deployment:
                    continue
                spec = deployment["spec"]
                values = source["helm"]["valuesObject"]
                expected_image = f"{values['image']['repository']}:{values['image']['tag']}"
                running_image = spec["template"]["spec"]["containers"][0]["image"]
                observed = deployment.get("status", {})
                if (
                    running_image == expected_image
                    and observed.get("observedGeneration", 0)
                    >= deployment["metadata"]["generation"]
                    and observed.get("updatedReplicas", 0) == values["replicas"]
                    and observed.get("availableReplicas", 0) == values["replicas"]
                ):
                    pending.remove(expected)
                    print(f"{name}: ready", file=sys.stderr, flush=True)
            if pending:
                time.sleep(3)
        if pending:
            details = "; ".join(
                f"{app['metadata']['name']}: "
                f"{last_progress.get(app['metadata']['name'], 'not observed')}"
                for app in pending
            )
            raise TimeoutError(
                f"Applications did not reach the requested healthy release: {details}"
            )

    def verify(self):
        # Readiness includes /health; also check it directly inside the backend pod.
        self.run(
            "--namespace",
            self.namespace,
            "exec",
            "deployment/backend",
            "--",
            "python",
            "-c",
            "from urllib.request import urlopen; "
            "assert urlopen('http://127.0.0.1:8000/health', timeout=10).status == 200",
        )
        with tempfile.TemporaryFile(mode="w+") as log:
            forward = subprocess.Popen(
                [
                    "kubectl",
                    "--context",
                    self.context,
                    "--namespace",
                    self.namespace,
                    "port-forward",
                    "service/frontend",
                    "0:80",
                    "--address=127.0.0.1",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if forward.poll() is not None:
                        raise RuntimeError("frontend port-forward exited")
                    log.seek(0)
                    match = re.search(r"Forwarding from 127\.0\.0\.1:(\d+)", log.read())
                    if match:
                        break
                    time.sleep(0.2)
                else:
                    raise TimeoutError("frontend port-forward did not start")
                environment = os.environ.copy()
                environment["IDEA_BOARD_BASE_URL"] = f"http://127.0.0.1:{match.group(1)}"
                test = Path(__file__).resolve().parents[2] / "apps/frontend/tests/stack.mjs"
                subprocess.run(["node", "--test", str(test)], env=environment, check=True)
            finally:
                forward.terminate()
                try:
                    forward.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    forward.kill()
                    forward.wait()

    def public_url(self, timeout=300):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ingress = self.get("ingress", "frontend", self.namespace)
            addresses = (ingress or {}).get("status", {}).get("loadBalancer", {}).get("ingress", [])
            if addresses:
                address = addresses[0].get("hostname") or addresses[0].get("ip")
                if address:
                    url = f"http://{address}"
                    try:
                        with urlopen(url, timeout=10) as response:
                            if response.status == 200:
                                with urlopen(
                                    url + "/api/ideas?limit=1", timeout=10
                                ) as api_response:
                                    if api_response.status == 200 and isinstance(
                                        json.load(api_response), list
                                    ):
                                        return url
                    except OSError:
                        pass  # Cloud load balancers can publish an address before serving traffic.
            time.sleep(5)
        raise TimeoutError("Ingress did not serve both the frontend and API")
