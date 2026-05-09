"""Tests for resolve_source.py — PR/MR branch resolution logic.

These tests mock CLI calls (gh, glab, git) to test the decision-making
around merged PRs with deleted branches and verify ref=None flows
correctly through caller chains.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_resolve_pr_info_merged_returns_none_ref():
    from resolve_source import _resolve_pr_info

    pr_url = "https://github.com/opendatahub-io/kubeflow/pull/751"
    fake_response = json.dumps(
        {"headRefName": "feat/mlflow-workbench-integration", "state": "MERGED"}
    )

    with patch("resolve_source._run_gh", return_value=fake_response):
        repo_url, ref = _resolve_pr_info(pr_url)

    assert repo_url == "https://github.com/opendatahub-io/kubeflow.git"
    assert ref is None


def test_resolve_pr_info_open_returns_branch():
    from resolve_source import _resolve_pr_info

    pr_url = "https://github.com/opendatahub-io/kubeflow/pull/800"
    fake_response = json.dumps(
        {"headRefName": "feat/new-feature", "state": "OPEN"}
    )

    with patch("resolve_source._run_gh", return_value=fake_response):
        repo_url, ref = _resolve_pr_info(pr_url)

    assert repo_url == "https://github.com/opendatahub-io/kubeflow.git"
    assert ref == "feat/new-feature"


def test_resolve_pr_info_closed_returns_branch():
    from resolve_source import _resolve_pr_info

    pr_url = "https://github.com/org/repo/pull/99"
    fake_response = json.dumps(
        {"headRefName": "fix/abandoned", "state": "CLOSED"}
    )

    with patch("resolve_source._run_gh", return_value=fake_response):
        repo_url, ref = _resolve_pr_info(pr_url)

    assert repo_url == "https://github.com/org/repo.git"
    assert ref == "fix/abandoned"


def test_resolve_mr_info_merged_returns_none_ref():
    from resolve_source import _resolve_mr_info

    mr_url = "https://gitlab.example.com/group/project/-/merge_requests/42"
    fake_response = json.dumps(
        {"source_branch": "feat/old-branch", "state": "merged"}
    )

    with patch("resolve_source._run_glab", return_value=fake_response):
        repo_url, ref = _resolve_mr_info(mr_url)

    assert repo_url == "https://gitlab.example.com/group/project.git"
    assert ref is None


def test_resolve_mr_info_opened_returns_branch():
    from resolve_source import _resolve_mr_info

    mr_url = "https://gitlab.example.com/group/project/-/merge_requests/43"
    fake_response = json.dumps(
        {"source_branch": "feat/active-branch", "state": "opened"}
    )

    with patch("resolve_source._run_glab", return_value=fake_response):
        repo_url, ref = _resolve_mr_info(mr_url)

    assert repo_url == "https://gitlab.example.com/group/project.git"
    assert ref == "feat/active-branch"


# --- Regression tests: ref=None flows through caller chains ---


def _make_git_result(returncode=0, stdout="", stderr=""):
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_resolve_discovered_repos_merged_pr_clones_default_branch(tmp_path):
    """When graph walker discovers a repo via a merged PR,
    _resolve_discovered_repos should clone with ref=None (default branch)
    and write source.yaml without a ref line."""
    from resolve_source import _resolve_discovered_repos

    discovered = [
        {
            "repo_url": "https://github.com/org/repo.git",
            "pr_urls": ["https://github.com/org/repo/pull/42"],
        }
    ]

    merged_response = json.dumps(
        {"headRefName": "feat/deleted-branch", "state": "MERGED"}
    )

    with (
        patch("resolve_source._run_gh", return_value=merged_response),
        patch("resolve_source._clone_repo", return_value=True) as mock_clone,
    ):
        result = _resolve_discovered_repos(discovered, tmp_path)

    assert result["status"] == "resolved"
    assert result["ref"] is None
    mock_clone.assert_called_once_with(
        "https://github.com/org/repo.git",
        tmp_path / "code-repo" / "repo",
        None,
    )

    source_yaml = (tmp_path / "source.yaml").read_text()
    assert "repo: https://github.com/org/repo.git" in source_yaml
    assert "ref:" not in source_yaml


def test_resolve_discovered_repos_open_pr_clones_branch(tmp_path):
    """When graph walker discovers a repo via an open PR,
    _resolve_discovered_repos should clone with the PR branch."""
    from resolve_source import _resolve_discovered_repos

    discovered = [
        {
            "repo_url": "https://github.com/org/repo.git",
            "pr_urls": ["https://github.com/org/repo/pull/99"],
        }
    ]

    open_response = json.dumps(
        {"headRefName": "feat/active-work", "state": "OPEN"}
    )

    with (
        patch("resolve_source._run_gh", return_value=open_response),
        patch("resolve_source._clone_repo", return_value=True) as mock_clone,
    ):
        result = _resolve_discovered_repos(discovered, tmp_path)

    assert result["status"] == "resolved"
    assert result["ref"] == "feat/active-work"
    mock_clone.assert_called_once_with(
        "https://github.com/org/repo.git",
        tmp_path / "code-repo" / "repo",
        "feat/active-work",
    )

    source_yaml = (tmp_path / "source.yaml").read_text()
    assert "ref: feat/active-work" in source_yaml


def test_resolve_multiple_prs_merged_clones_default_branch(tmp_path):
    """When _resolve_multiple_prs gets a merged PR, it should clone
    with ref=None and not write a stale ref to source.yaml."""
    from resolve_source import _resolve_multiple_prs

    pr_urls = ["https://github.com/org/repo/pull/42"]
    merged_response = json.dumps(
        {"headRefName": "feat/old-branch", "state": "MERGED"}
    )

    with (
        patch("resolve_source._run_gh", return_value=merged_response),
        patch("resolve_source._clone_repo", return_value=True) as mock_clone,
    ):
        result = _resolve_multiple_prs(pr_urls, tmp_path)

    assert result["status"] == "resolved"
    assert result["ref"] is None
    mock_clone.assert_called_once_with(
        "https://github.com/org/repo.git",
        tmp_path / "code-repo" / "repo",
        None,
    )

    source_yaml = (tmp_path / "source.yaml").read_text()
    assert "ref:" not in source_yaml


def test_write_source_yaml_omits_ref_when_none(tmp_path):
    """_write_source_yaml should not write a ref line when ref is None."""
    from resolve_source import _write_source_yaml

    _write_source_yaml(tmp_path, "https://github.com/org/repo.git", None)

    source_yaml = (tmp_path / "source.yaml").read_text()
    assert "repo: https://github.com/org/repo.git" in source_yaml
    assert "ref:" not in source_yaml


def test_write_source_yaml_includes_ref_when_present(tmp_path):
    """_write_source_yaml should write the ref line when ref is provided."""
    from resolve_source import _write_source_yaml

    _write_source_yaml(tmp_path, "https://github.com/org/repo.git", "feat/branch")

    source_yaml = (tmp_path / "source.yaml").read_text()
    assert "repo: https://github.com/org/repo.git" in source_yaml
    assert "ref: feat/branch" in source_yaml
