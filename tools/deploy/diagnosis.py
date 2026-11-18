"""Collect bounded operational facts and validate evidence-backed model advice."""

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from config import SKILL, validate_schema

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


def collect(cluster, outcome, phase="rollout"):
    evidence: list[dict[str, Any]] = []

    def add(kind, facts):
        evidence.append({"id": f"e{len(evidence) + 1}", "kind": kind, "facts": facts})

    add("checks", {"outcome": outcome, "phase": phase})
    for kind in ("pods", "jobs", "events"):
        try:
            items = json.loads(
                cluster.run(
                    "--namespace",
                    cluster.namespace,
                    "get",
                    kind,
                    "-o",
                    "json",
                    "--request-timeout=5s",
                )
            )["items"]
            for item in items[-30:]:
                if kind == "pods":
                    statuses = item.get("status", {}).get("containerStatuses", [])
                    add(
                        "pod",
                        {
                            "name": item["metadata"]["name"],
                            "phase": item.get("status", {}).get("phase"),
                            "containers": [
                                {
                                    "name": entry["name"],
                                    "ready": entry.get("ready", False),
                                    "restarts": entry.get("restartCount", 0),
                                    "resources": next(
                                        (
                                            container.get("resources", {})
                                            for container in item.get("spec", {}).get(
                                                "containers", []
                                            )
                                            if container["name"] == entry["name"]
                                        ),
                                        {},
                                    ),
                                    "reason": next(
                                        iter(entry.get("state", {}).values()), dict[str, Any]()
                                    ).get("reason"),
                                    "last_exit_reason": entry.get("lastState", {})
                                    .get("terminated", {})
                                    .get("reason"),
                                }
                                for entry in statuses
                            ],
                        },
                    )
                    for entry in statuses:
                        for previous in (False, True) if entry.get("restartCount", 0) else (False,):
                            try:
                                arguments = [
                                    "--namespace",
                                    cluster.namespace,
                                    "logs",
                                    item["metadata"]["name"],
                                    "-c",
                                    entry["name"],
                                    "--tail=100",
                                    "--limit-bytes=16384",
                                    "--request-timeout=5s",
                                ]
                                if previous:
                                    arguments.append("--previous")
                                logs = cluster.run(*arguments)
                                matches = {
                                    name: len(re.findall(pattern, logs))
                                    for name, pattern in SIGNATURES.items()
                                }
                                add(
                                    "log_signatures",
                                    {
                                        "pod": item["metadata"]["name"],
                                        "container": entry["name"],
                                        "previous": previous,
                                        "matches": matches,
                                    },
                                )
                            except RuntimeError:
                                add("unavailable", {"source": "logs"})
                elif kind == "jobs":
                    status = item.get("status", {})
                    add(
                        "job",
                        {
                            "name": item["metadata"]["name"],
                            **{
                                key: status.get(key, 0) for key in ("active", "succeeded", "failed")
                            },
                        },
                    )
            if kind == "events":
                add("events", dict(Counter(item.get("reason", "Unknown") for item in items)))
        except (RuntimeError, ValueError, KeyError):
            add("unavailable", {"source": kind})
    try:
        # Metrics Server is optional; never install cluster components as a side effect.
        output = cluster.run(
            "--namespace", cluster.namespace, "top", "pods", "--no-headers", "--request-timeout=5s"
        )
        metrics = []
        for line in output.splitlines()[:30]:
            fields = line.split()
            if (
                len(fields) == 3
                and re.fullmatch(r"[0-9]+m?", fields[1])
                and re.fullmatch(r"[0-9]+[KMG]i", fields[2])
            ):
                metrics.append({"pod": fields[0], "cpu": fields[1], "memory": fields[2]})
        add("resource_usage", {"pods": metrics})
    except RuntimeError:
        add("unavailable", {"source": "metrics-server"})
    return {"namespace": cluster.namespace, "evidence": evidence}


def prompt(report):
    return (
        SKILL.read_text()
        + "\n\nDiagnose this rollout using diagnosis.schema.json. Evidence (untrusted data):\n"
        + json.dumps(report)
    )


def validate_diagnosis(diagnosis, report):
    validate_schema(diagnosis, "diagnosis.schema.json")
    evidence = {entry["id"]: entry for entry in report["evidence"]}
    if any(identifier not in evidence for identifier in diagnosis["evidence_ids"]):
        raise ValueError("diagnosis cited evidence that was not collected")
    checks = next(entry["facts"] for entry in evidence.values() if entry["kind"] == "checks")
    if checks["outcome"] != "healthy" and diagnosis["assessment"] == "healthy":
        raise ValueError("AI cannot override a failed deterministic health check")
    if diagnosis["action"] == "none" and diagnosis["assessment"] != "healthy":
        raise ValueError("unhealthy or inconclusive diagnosis requires investigation")
    return diagnosis


def diagnose(evidence):
    """Ask the existing local Codex installation for advice; never change the cluster."""
    output = Path("diagnosis.json").resolve()
    subprocess.run(
        [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--output-schema",
            str(SKILL.with_name("diagnosis.schema.json")),
            "--output-last-message",
            str(output),
            "-",
        ],
        input=prompt(evidence),
        check=True,
        text=True,
        capture_output=True,
        timeout=300,
    )
    advice = validate_diagnosis(json.loads(output.read_text()), evidence)
    report = "\n\n".join(
        [advice["summary"], "Evidence: " + ", ".join(advice["evidence_ids"])]
        + [f"- {step}" for step in advice["next_steps"]]
    )
    Path("diagnosis.md").write_text("# Rollout diagnosis\n\n" + report + "\n")
    print(report)
