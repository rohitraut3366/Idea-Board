"""Explicit model-output fixtures; these do not represent live model calls."""


def recommendation(cloud="kind", environment="staging"):
    replicas = 2 if environment == "production" else 1
    infrastructure = None
    if cloud != "kind" and environment != "preview":
        infrastructure = {
            "node_count": 2,
            "node_size": "t3.medium" if cloud == "aws" else "e2-standard-2",
            "database_size": "db.t4g.micro" if cloud == "aws" else "db-custom-1-3840",
            "database_storage_gb": 20,
            "database_high_availability": environment == "production",
            "reason": "Two workers; standby reserved for production availability.",
        }
    return {
        "reason": "Low expected traffic; validate memory and latency under concurrent load.",
        "backend": {
            "replicas": replicas,
            "cpu_millicores": 100,
            "memory_request_mib": 128,
            "memory_limit_mib": 256,
        },
        "frontend": {
            "replicas": replicas,
            "cpu_millicores": 50,
            "memory_request_mib": 32,
            "memory_limit_mib": 128,
        },
        "infrastructure": infrastructure,
        "steps": [
            {"action": action, "reason": reason}
            for action, reason in (
                ("render", "Validate and render the desired state."),
                ("sync_backend", "Apply database migrations and wait for the backend."),
                ("sync_frontend", "Start the frontend after its upstream Service exists."),
                (
                    "verify",
                    "Check Argo status, the requested images, and full-stack HTTP behavior.",
                ),
            )
        ],
    }
