import json
from copy import deepcopy
from pathlib import Path

import pytest
from recommendations import recommendation

from config import Target, manifests, terraform_variables, validate_recommendation
from planning import prepare

SHA = "a" * 40


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_generated_sizing_uses_existing_terraform_inputs(cloud, tmp_path):
    target = Target(cloud, "production", SHA, SHA)
    proposal = recommendation(cloud, "production")
    prepare(target, proposal, tmp_path, Path("recommendation.json"))
    generated = terraform_variables(target, proposal)
    assert generated["cluster"]["node_count"] == 2
    assert (
        generated["applications/idea-board"][
            "database_multi_az" if cloud == "aws" else "database_regional"
        ]
        is True
    )
    assert sum(len(values) for values in generated.values()) == 5
    region = "ap-southeast-2" if cloud == "aws" else "australia-southeast1"
    root = Path(__file__).resolve().parents[3] / "infra/terraform" / cloud / "staging" / region
    plan = (tmp_path / "plan.md").read_text()
    for project, values in generated.items():
        path = tmp_path / "terraform" / project / "sizing.tfvars.json"
        assert json.loads(path.read_text()) == values
        definitions = (root / project / "variables.tf").read_text()
        for key in values:
            assert f'variable "{key}"' in definitions
        assert f"PROJECT={cloud}/production/YOUR_REGION/{project}" in plan
    applications = json.loads((tmp_path / "applications.json").read_text())["items"]
    assert applications == manifests(target, proposal)
    assert "terraform" in (tmp_path / "plan.md").read_text()


def test_model_can_size_services_independently():
    proposal = recommendation()
    proposal["backend"].update(
        replicas=3, cpu_millicores=350, memory_request_mib=320, memory_limit_mib=768
    )
    _, backend, frontend = manifests(Target("kind", "staging", SHA, SHA), proposal)
    backend_values = backend["spec"]["source"]["helm"]["valuesObject"]
    frontend_values = frontend["spec"]["source"]["helm"]["valuesObject"]
    assert backend_values["replicas"] == 3 and frontend_values["replicas"] == 1
    assert backend_values["resources"] == {
        "requests": {"cpu": "350m", "memory": "320Mi"},
        "limits": {"memory": "768Mi"},
    }


@pytest.mark.parametrize(
    "mutation", ["memory", "order", "cloud", "zones", "availability", "extra", "injection"]
)
def test_invalid_configuration_fails_before_rendering(mutation):
    proposal = recommendation("gcp", "production")
    if mutation == "memory":
        proposal["backend"]["memory_limit_mib"] = 64
    elif mutation == "order":
        proposal["steps"].reverse()
    elif mutation == "cloud":
        proposal["infrastructure"]["node_size"] = "t3.medium"
    elif mutation == "zones":
        proposal["infrastructure"]["node_count"] = 3
    elif mutation == "availability":
        proposal["infrastructure"]["database_high_availability"] = False
    elif mutation == "extra":
        proposal["infrastructure"]["deletion_protection"] = False
    else:
        proposal["steps"][0]["action"] = "kubectl delete ns default"
    with pytest.raises(ValueError):
        validate_recommendation(proposal, "production", "gcp")


def test_preview_does_not_generate_shared_infrastructure(tmp_path):
    prepare(
        Target("aws", "staging", SHA, SHA),
        recommendation("aws"),
        tmp_path,
        Path("recommendation.json"),
    )
    target = Target("aws", "preview", SHA, SHA, 42)
    proposal = recommendation("aws", "preview")
    assert terraform_variables(target, proposal) is None
    prepare(target, proposal, tmp_path, Path("recommendation.json"))
    assert not list(tmp_path.rglob("*.tfvars.json"))
    invalid = deepcopy(proposal)
    invalid["infrastructure"] = recommendation("aws")["infrastructure"]
    with pytest.raises(ValueError, match="shared infrastructure"):
        prepare(target, invalid, tmp_path, Path("recommendation.json"))


def test_json_schema_integer_is_rendered_as_a_kubernetes_integer():
    proposal = recommendation()
    # JSON Schema accepts an integral float, while Kubernetes replicas requires an integer.
    proposal["backend"]["replicas"] = 2.0
    backend = manifests(Target("kind", "staging", SHA, SHA), proposal)[1]
    assert type(backend["spec"]["source"]["helm"]["valuesObject"]["replicas"]) is int
