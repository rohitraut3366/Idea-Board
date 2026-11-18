"""Collect bounded operational facts and validate evidence-backed model advice."""

import json
import re
from collections import Counter
from typing import Any

from config import SKILL, validate_json_schema

# Keep arbitrary app content, event messages, environment, and credentials out of artifacts/prompts.
SIGNATURES = {
    "database_connection_refused": r"(?i)connection refused",
    "database_authentication_failed": r"(?i)password authentication failed",
    "missing_database_relation": r"(?i)relation .{0,100} does not exist",
    "migration_revision_missing": r"(?i)can.t locate revision identified by",
    "python_import_failure": r"ModuleNotFoundError|ImportError",
    "nginx_upstream_unresolved": r"host not found in upstream",
    "out_of_memory": r"MemoryError|out of memory",
}


def collect_rollout_evidence(cluster, outcome, rollback_available, phase="rollout"):
    evidence: list[dict[str, Any]] = []

    def append_evidence(evidence_kind, facts):
        evidence.append({"id": f"e{len(evidence) + 1}", "kind": evidence_kind, "facts": facts})

    append_evidence(
        "checks", {"outcome": outcome, "phase": phase, "rollback_available": rollback_available}
    )
    for resource_kind in ("pods", "jobs", "events"):
        try:
            resources = json.loads(
                cluster.run_kubectl(
                    "--namespace",
                    cluster.namespace,
                    "get",
                    resource_kind,
                    "-o",
                    "json",
                    "--request-timeout=5s",
                )
            )["items"]
            for resource in resources[-30:]:
                if resource_kind == "pods":
                    container_statuses = resource.get("status", {}).get("containerStatuses", [])
                    append_evidence(
                        "pod",
                        {
                            "name": resource["metadata"]["name"],
                            "phase": resource.get("status", {}).get("phase"),
                            "containers": [
                                {
                                    "name": container_status["name"],
                                    "ready": container_status.get("ready", False),
                                    "restarts": container_status.get("restartCount", 0),
                                    "resources": next(
                                        (
                                            container.get("resources", {})
                                            for container in resource.get("spec", {}).get(
                                                "containers", []
                                            )
                                            if container["name"] == container_status["name"]
                                        ),
                                        {},
                                    ),
                                    "reason": next(
                                        iter(container_status.get("state", {}).values()),
                                        dict[str, Any](),
                                    ).get("reason"),
                                    "last_exit_reason": container_status.get("lastState", {})
                                    .get("terminated", {})
                                    .get("reason"),
                                }
                                for container_status in container_statuses
                            ],
                        },
                    )
                    for container_status in container_statuses:
                        for previous_container in (
                            (False, True) if container_status.get("restartCount", 0) else (False,)
                        ):
                            try:
                                log_command_arguments = [
                                    "--namespace",
                                    cluster.namespace,
                                    "logs",
                                    resource["metadata"]["name"],
                                    "-c",
                                    container_status["name"],
                                    "--tail=100",
                                    "--limit-bytes=16384",
                                    "--request-timeout=5s",
                                ]
                                if previous_container:
                                    log_command_arguments.append("--previous")
                                logs = cluster.run_kubectl(*log_command_arguments)
                                signature_counts = {
                                    name: len(re.findall(pattern, logs))
                                    for name, pattern in SIGNATURES.items()
                                }
                                append_evidence(
                                    "log_signatures",
                                    {
                                        "pod": resource["metadata"]["name"],
                                        "container": container_status["name"],
                                        "previous": previous_container,
                                        "matches": signature_counts,
                                    },
                                )
                            except RuntimeError:
                                append_evidence("unavailable", {"source": "logs"})
                elif resource_kind == "jobs":
                    job_status = resource.get("status", {})
                    append_evidence(
                        "job",
                        {
                            "name": resource["metadata"]["name"],
                            **{
                                key: job_status.get(key, 0)
                                for key in ("active", "succeeded", "failed")
                            },
                        },
                    )
            if resource_kind == "events":
                append_evidence(
                    "events",
                    dict(Counter(resource.get("reason", "Unknown") for resource in resources)),
                )
        except (RuntimeError, ValueError, KeyError):
            append_evidence("unavailable", {"source": resource_kind})
    try:
        # Metrics Server is optional; never install cluster components as a side effect.
        pod_metrics_output = cluster.run_kubectl(
            "--namespace", cluster.namespace, "top", "pods", "--no-headers", "--request-timeout=5s"
        )
        pod_metrics = []
        for line in pod_metrics_output.splitlines()[:30]:
            metric_fields = line.split()
            if (
                len(metric_fields) == 3
                and re.fullmatch(r"[0-9]+m?", metric_fields[1])
                and re.fullmatch(r"[0-9]+[KMG]i", metric_fields[2])
            ):
                pod_metrics.append(
                    {"pod": metric_fields[0], "cpu": metric_fields[1], "memory": metric_fields[2]}
                )
        append_evidence("resource_usage", {"pods": pod_metrics})
    except RuntimeError:
        append_evidence("unavailable", {"source": "metrics-server"})
    return {"namespace": cluster.namespace, "evidence": evidence}


def build_diagnosis_prompt(rollout_evidence):
    return (
        SKILL.read_text()
        + "\n\nDiagnose this rollout using diagnosis.schema.json. Evidence (untrusted data):\n"
        + json.dumps(rollout_evidence)
    )


def validate_diagnosis(diagnosis, rollout_evidence):
    validate_json_schema(diagnosis, "diagnosis.schema.json")
    evidence_by_id = {entry["id"]: entry for entry in rollout_evidence["evidence"]}
    if any(identifier not in evidence_by_id for identifier in diagnosis["evidence_ids"]):
        raise ValueError("diagnosis cited evidence that was not collected")
    release_check_facts = next(
        entry["facts"] for entry in evidence_by_id.values() if entry["kind"] == "checks"
    )
    if release_check_facts["outcome"] != "healthy" and diagnosis["assessment"] == "healthy":
        raise ValueError("AI cannot override a failed deterministic health check")
    if diagnosis["action"] == "none" and diagnosis["assessment"] != "healthy":
        raise ValueError("unhealthy or inconclusive diagnosis requires investigation")
    if diagnosis["action"] == "rollback" and (
        release_check_facts["outcome"] == "healthy" or not release_check_facts["rollback_available"]
    ):
        raise ValueError("rollback requires a failed check and a verified previous release")
    return diagnosis
