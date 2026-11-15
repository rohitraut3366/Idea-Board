from copy import deepcopy
from unittest.mock import Mock

import pytest

from github import check_release, preview_matrix

REPO = "rohitraut3366/Idea-Board"
SHA = "a" * 40


def pull():
    return {"number": 12, "state": "open", "head": {"sha": SHA, "repo": {"full_name": REPO}}}


def event():
    return {
        "workflow_run": {
            "conclusion": "success",
            "event": "pull_request",
            "head_sha": SHA,
            "head_repository": {"full_name": REPO},
        }
    }


def test_previews_are_disabled_until_cloud_is_configured():
    assert preview_matrix(event(), "workflow_run", REPO, "") == []


@pytest.mark.parametrize("case", ["fork", "failure", "push"])
def test_untrusted_or_unsuccessful_runs_cannot_deploy(monkeypatch, case):
    run = event()
    if case == "fork":
        run["workflow_run"]["head_repository"]["full_name"] = "someone/fork"
    elif case == "failure":
        run["workflow_run"]["conclusion"] = "failure"
    else:
        run["workflow_run"]["event"] = "push"
    api = Mock()
    monkeypatch.setattr("github.api", api)
    assert preview_matrix(run, "workflow_run", REPO, "aws") == []
    api.assert_not_called()


def test_only_current_open_prs_are_selected(monkeypatch):
    old = deepcopy(pull())
    old["head"]["sha"] = "b" * 40
    closed = deepcopy(pull())
    closed["state"] = "closed"
    monkeypatch.setattr("github.api", Mock(return_value=[old, closed, pull()]))
    assert preview_matrix(event(), "workflow_run", REPO, "gcp") == [
        {
            "pr": 12,
            "cloud": "gcp",
            "image_tag": SHA,
            "operation": "release",
        }
    ]


def test_closed_pr_selects_cleanup_without_ai_or_ci_query(monkeypatch):
    api = Mock()
    monkeypatch.setattr("github.api", api)
    assert (
        preview_matrix(
            {"pull_request": pull(), "action": "closed"}, "pull_request_target", REPO, "aws"
        )[0]["operation"]
        == "cleanup"
    )
    api.assert_not_called()


def test_release_rechecks_that_pr_has_not_closed(monkeypatch):
    closed = pull()
    closed["state"] = "closed"
    monkeypatch.setattr("github.api", Mock(return_value=closed))
    with pytest.raises(ValueError, match="open"):
        check_release(REPO, SHA, "preview", 12)


def test_release_requires_a_successful_ci_run(monkeypatch):
    monkeypatch.setattr("github.api", Mock(return_value={"workflow_runs": []}))
    with pytest.raises(ValueError, match="no successful CI"):
        check_release(REPO, SHA, "staging")
