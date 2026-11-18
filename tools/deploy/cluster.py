"""Argo CD deployment and verification with an explicit Kubernetes context."""

import base64
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from config import get_application_chart_source


class Cluster:
    def __init__(self, context, namespace):
        if not context:
            raise ValueError("an explicit Kubernetes context is required")
        self.context = context
        self.namespace = namespace

    def run_kubectl(self, *arguments, data=None):
        command_result = subprocess.run(
            ["kubectl", "--context", self.context, *arguments],
            input=data if isinstance(data, str) else json.dumps(data) if data is not None else None,
            text=True,
            capture_output=True,
        )
        if command_result.returncode:
            # Do not include stdin: it may contain database credentials.
            raise RuntimeError(f"kubectl {arguments[0]} failed: {command_result.stderr.strip()}")
        return command_result.stdout

    def get_resource(self, kind, name, namespace=None):
        arguments = ["get", kind, name, "--ignore-not-found", "-o", "json"]
        if namespace:
            arguments += ["--namespace", namespace]
        output = self.run_kubectl(*arguments)
        return json.loads(output) if output.strip() else None

    def apply_resource(self, resource_manifest, force=False):
        self.run_kubectl(
            "apply",
            "--server-side",
            "--field-manager=idea-board-deploy",
            *(["--force-conflicts"] if force else []),
            "-f",
            "-",
            data=resource_manifest,
        )

    def ensure_namespace(self, environment):
        existing_namespace = self.get_resource("namespace", self.namespace)
        labels = {
            "app.kubernetes.io/part-of": "idea-board",
            "idea-board/environment": environment,
        }
        if existing_namespace:
            existing_labels = existing_namespace["metadata"].get("labels", {})
            if any(existing_labels.get(key) != value for key, value in labels.items()):
                raise ValueError("namespace is not owned by this deployment tool")
        else:
            self.apply_resource(
                {
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {"name": self.namespace, "labels": labels},
                }
            )

    def read_database_url(self):
        database_secret = self.get_resource("secret", "idea-board-database", self.namespace)
        if not database_secret:
            return None
        return base64.b64decode(database_secret["data"]["DATABASE_URL"]).decode()

    def wait_for_application_health(self, applications, timeout=600):
        """Wait for the requested Argo sources, sync/health, image, and replica rollout."""
        deadline = time.monotonic() + timeout
        pending_applications = applications.copy()
        while pending_applications and time.monotonic() < deadline:
            for expected_application in pending_applications.copy():
                application_name = expected_application["metadata"]["name"]
                current_application = self.get_resource("application", application_name, "argocd")
                if not current_application:
                    continue
                application_status = current_application.get("status", {})
                if "operation" in expected_application:
                    operation_state = application_status.get("operationState", {})
                    if (
                        operation_state.get("operation", {}).get("info")
                        != expected_application["operation"]["info"]
                        or operation_state.get("phase") != "Succeeded"
                    ):
                        continue
                expected_chart_source = get_application_chart_source(expected_application)
                compared_chart_source = (
                    application_status.get("sync", {}).get("comparedTo", {}).get("source", {})
                )
                source_matches = (
                    all(
                        compared_chart_source.get(key) == expected_chart_source[key]
                        for key in (
                            "repoURL",
                            "targetRevision",
                            "path",
                        )
                    )
                    and compared_chart_source.get("helm", {}).get("valuesObject")
                    == expected_chart_source["helm"]["valuesObject"]
                )
                synced_revision = application_status.get("sync", {}).get("revision")
                if "sources" in expected_application["spec"]:
                    source_matches = (
                        application_status.get("sync", {}).get("comparedTo", {}).get("sources")
                        == expected_application["spec"]["sources"]
                    )
                    synced_revisions = application_status.get("sync", {}).get("revisions", [])
                    synced_revision = synced_revisions[0] if synced_revisions else None
                is_parent_application = expected_chart_source["path"] == "gitops/applications"
                if not source_matches or (
                    (
                        not is_parent_application
                        or re.fullmatch(r"[0-9a-f]{40}", expected_chart_source["targetRevision"])
                    )
                    and synced_revision != expected_chart_source["targetRevision"]
                ):
                    continue
                if (
                    application_status.get("sync", {}).get("status") != "Synced"
                    or application_status.get("health", {}).get("status") != "Healthy"
                ):
                    continue
                if is_parent_application:
                    # Child readiness is checked separately, after the parent has reconciled.
                    if application_status.get("operationState", {}).get("phase") != "Succeeded":
                        continue
                    pending_applications.remove(expected_application)
                    continue
                helm_release_name = expected_chart_source["helm"]["releaseName"]
                deployment = self.get_resource("deployment", helm_release_name, self.namespace)
                if not deployment:
                    continue
                deployment_spec = deployment["spec"]
                helm_values = expected_chart_source["helm"]["valuesObject"]
                expected_image = (
                    f"{helm_values['image']['repository']}:{helm_values['image']['tag']}"
                )
                deployment_image = deployment_spec["template"]["spec"]["containers"][0]["image"]
                deployment_status = deployment.get("status", {})
                if (
                    deployment_image == expected_image
                    and deployment_status.get("observedGeneration", 0)
                    >= deployment["metadata"]["generation"]
                    and deployment_status.get("updatedReplicas", 0) == helm_values["replicas"]
                    and deployment_status.get("availableReplicas", 0) == helm_values["replicas"]
                ):
                    pending_applications.remove(expected_application)
            if pending_applications:
                time.sleep(3)
        if pending_applications:
            pending_application_names = ", ".join(
                application["metadata"]["name"] for application in pending_applications
            )
            raise TimeoutError(
                "Applications did not reach the requested healthy release: "
                f"{pending_application_names}"
            )

    def verify_application_http(self):
        """Check backend health and run frontend/API stack tests through a port-forward."""
        # Readiness includes /health; also check it directly inside the backend pod.
        self.run_kubectl(
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
        with tempfile.TemporaryFile(mode="w+") as port_forward_log:
            port_forward_process = subprocess.Popen(
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
                stdout=port_forward_log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if port_forward_process.poll() is not None:
                        raise RuntimeError("frontend port-forward exited")
                    port_forward_log.seek(0)
                    forwarded_port_match = re.search(
                        r"Forwarding from 127\.0\.0\.1:(\d+)", port_forward_log.read()
                    )
                    if forwarded_port_match:
                        break
                    time.sleep(0.2)
                else:
                    raise TimeoutError("frontend port-forward did not start")
                test_environment = os.environ.copy()
                test_environment["IDEA_BOARD_BASE_URL"] = (
                    f"http://127.0.0.1:{forwarded_port_match.group(1)}"
                )
                stack_test_path = (
                    Path(__file__).resolve().parents[2] / "apps/frontend/tests/stack.mjs"
                )
                subprocess.run(
                    ["node", "--test", str(stack_test_path)], env=test_environment, check=True
                )
            finally:
                port_forward_process.terminate()
                try:
                    port_forward_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    port_forward_process.kill()
                    port_forward_process.wait()

    def wait_for_public_http(self, timeout=300):
        """Wait for the ingress to serve the page and API, then return its URL."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ingress = self.get_resource("ingress", "frontend", self.namespace)
            ingress_addresses = (
                (ingress or {}).get("status", {}).get("loadBalancer", {}).get("ingress", [])
            )
            if ingress_addresses:
                ingress_address = ingress_addresses[0].get("hostname") or ingress_addresses[0].get(
                    "ip"
                )
                if ingress_address:
                    public_url = f"http://{ingress_address}"
                    try:
                        with urlopen(public_url, timeout=10) as response:
                            if response.status == 200:
                                with urlopen(
                                    public_url + "/api/ideas?limit=1", timeout=10
                                ) as api_response:
                                    if api_response.status == 200 and isinstance(
                                        json.load(api_response), list
                                    ):
                                        return public_url
                    except OSError:
                        pass  # Cloud load balancers can publish an address before serving traffic.
            time.sleep(5)
        raise TimeoutError("Ingress did not serve both the frontend and API")
