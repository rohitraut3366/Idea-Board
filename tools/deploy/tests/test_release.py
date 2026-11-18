import json
from unittest.mock import Mock

import pytest
from recommendations import recommendation

from config import Target
from deploy import release

SHA = "a" * 40


@pytest.mark.parametrize("failed_check", [None, "backend", "http"])
def test_release_reports_health_or_diagnoses_failure_without_saving_history(
    monkeypatch, tmp_path, failed_check
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    evidence = Mock(return_value={"evidence": []})
    diagnose = Mock()
    monkeypatch.setattr("diagnosis.collect", evidence)
    monkeypatch.setattr("diagnosis.diagnose", diagnose)
    cluster = Mock(namespace="idea-board-staging")
    cluster.get.return_value = None
    # A repeated local command must not leave a stale success result behind.
    (tmp_path / "deployment-result.json").write_text('{"status": "healthy"}')
    if failed_check == "backend":
        cluster.wait.side_effect = TimeoutError("backend failed")
    elif failed_check == "http":
        cluster.verify.side_effect = RuntimeError("HTTP failed")
    if failed_check:
        with pytest.raises((TimeoutError, RuntimeError)):
            release(cluster, Target("kind", "staging", SHA, SHA), recommendation())
        assert not (tmp_path / "deployment-result.json").exists()
        assert json.loads((tmp_path / "deployment-diagnostics.json").read_text()) == {
            "evidence": []
        }
        diagnose.assert_called_once_with(evidence.return_value)
        assert evidence.call_args.args[1] == "failed"
        if failed_check == "backend":
            cluster.verify.assert_not_called()
    else:
        release(cluster, Target("kind", "staging", SHA, SHA), recommendation())
        assert json.loads((tmp_path / "deployment-result.json").read_text())["status"] == "healthy"
        evidence.assert_not_called()
        diagnose.assert_not_called()
    assert not any(call.args[0]["kind"] == "ConfigMap" for call in cluster.apply.call_args_list)
    assert not any(call.args[0] == "configmap" for call in cluster.get.call_args_list)


@pytest.mark.parametrize("github_actions", [False, True])
def test_ai_failure_cannot_hide_the_release_failure(monkeypatch, tmp_path, github_actions, capsys):
    monkeypatch.chdir(tmp_path)
    if github_actions:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
    else:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr("diagnosis.collect", Mock(return_value={"evidence": []}))
    diagnose = Mock(side_effect=FileNotFoundError("codex missing"))
    monkeypatch.setattr("diagnosis.diagnose", diagnose)
    cluster = Mock(namespace="idea-board-staging")
    cluster.get.return_value = None
    cluster.wait.side_effect = TimeoutError("backend failed")
    with pytest.raises(TimeoutError, match="backend failed"):
        release(cluster, Target("kind", "staging", SHA, SHA), recommendation())
    assert (tmp_path / "deployment-diagnostics.json").exists()
    if github_actions:
        diagnose.assert_not_called()  # The separate workflow job owns AI diagnosis.
    else:
        diagnose.assert_called_once()
        assert "AI diagnosis unavailable" in capsys.readouterr().err
