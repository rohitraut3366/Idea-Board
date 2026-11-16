import json
from unittest.mock import Mock

import pytest
from recommendations import recommendation

from config import Target
from deploy import release
from root import shared_root

SHA = "a" * 40


@pytest.mark.parametrize("failed_check", [None, "backend", "http"])
def test_checkpoint_is_promoted_only_after_rollout_and_http_pass(
    monkeypatch, tmp_path, failed_check
):
    monkeypatch.chdir(tmp_path)
    evidence = Mock(return_value={"evidence": []})
    monkeypatch.setattr("diagnosis.collect", evidence)
    cluster = Mock(namespace="idea-board-staging")
    root = shared_root(Target("kind", "staging", SHA, SHA), [])
    cluster.get.side_effect = lambda kind, name, *args: root if name == "idea-board" else None
    if failed_check == "backend":
        cluster.wait.side_effect = TimeoutError("backend failed")
    elif failed_check == "http":
        cluster.verify.side_effect = RuntimeError("HTTP failed")
    if failed_check:
        with pytest.raises((TimeoutError, RuntimeError)):
            release(cluster, Target("kind", "staging", SHA, SHA), recommendation())
        assert not (tmp_path / "deployment-result.json").exists()
    else:
        release(cluster, Target("kind", "staging", SHA, SHA), recommendation())
        assert json.loads((tmp_path / "deployment-result.json").read_text())["status"] == "healthy"
    snapshots = [
        json.loads(call.args[0]["data"]["release.json"])
        for call in cluster.apply.call_args_list
        if call.args[0]["kind"] == "ConfigMap"
    ]
    assert snapshots[0]["healthy"] is None
    assert snapshots[0]["attempt"]["image_tag"] == SHA
    if failed_check:
        assert len(snapshots) == 1
        assert evidence.call_args.args[1] == "failed"
    else:
        assert len(snapshots) == 2
        assert snapshots[-1]["healthy"] and snapshots[-1]["attempt"] is None
        assert evidence.call_args.args[1] == "healthy"
    credentials = next(
        call.args[0]["stringData"]
        for call in cluster.apply.call_args_list
        if call.args[0]["kind"] == "Secret"
    )
    assert credentials["POSTGRES_PASSWORD"] not in json.dumps(snapshots)
    cluster.run.assert_not_called()
