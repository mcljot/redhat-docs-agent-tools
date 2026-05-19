"""Tests for resolve_source.py — PR/MR branch resolution logic.

These tests mock CLI calls (gh, glab, git) to test the decision-making
around merged PRs with deleted branches and verify ref=None flows
correctly through caller chains.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch


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
    fake_response = json.dumps({"headRefName": "feat/new-feature", "state": "OPEN"})

    with patch("resolve_source._run_gh", return_value=fake_response):
        repo_url, ref = _resolve_pr_info(pr_url)

    assert repo_url == "https://github.com/opendatahub-io/kubeflow.git"
    assert ref == "feat/new-feature"


def test_resolve_pr_info_closed_returns_branch():
    from resolve_source import _resolve_pr_info

    pr_url = "https://github.com/org/repo/pull/99"
    fake_response = json.dumps({"headRefName": "fix/abandoned", "state": "CLOSED"})

    with patch("resolve_source._run_gh", return_value=fake_response):
        repo_url, ref = _resolve_pr_info(pr_url)

    assert repo_url == "https://github.com/org/repo.git"
    assert ref == "fix/abandoned"


def test_resolve_mr_info_merged_returns_none_ref():
    from resolve_source import _resolve_mr_info

    mr_url = "https://gitlab.example.com/group/project/-/merge_requests/42"
    fake_response = json.dumps({"source_branch": "feat/old-branch", "state": "merged"})

    with patch("resolve_source._run_glab", return_value=fake_response):
        repo_url, ref = _resolve_mr_info(mr_url)

    assert repo_url == "https://gitlab.example.com/group/project.git"
    assert ref is None


def test_resolve_mr_info_opened_returns_branch():
    from resolve_source import _resolve_mr_info

    mr_url = "https://gitlab.example.com/group/project/-/merge_requests/43"
    fake_response = json.dumps({"source_branch": "feat/active-branch", "state": "opened"})

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

    merged_response = json.dumps({"headRefName": "feat/deleted-branch", "state": "MERGED"})

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
        pr_url="https://github.com/org/repo/pull/42",
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

    open_response = json.dumps({"headRefName": "feat/active-work", "state": "OPEN"})

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
        pr_url="https://github.com/org/repo/pull/99",
    )

    source_yaml = (tmp_path / "source.yaml").read_text()
    assert "ref: feat/active-work" in source_yaml


def test_resolve_multiple_prs_merged_clones_default_branch(tmp_path):
    """When _resolve_multiple_prs gets a merged PR, it should clone
    with ref=None and not write a stale ref to source.yaml."""
    from resolve_source import _resolve_multiple_prs

    pr_urls = ["https://github.com/org/repo/pull/42"]
    merged_response = json.dumps({"headRefName": "feat/old-branch", "state": "MERGED"})

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
        pr_url="https://github.com/org/repo/pull/42",
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


# --- Tests for description URL extraction and smart-link handling ---


class TestCleanJiraUrl:
    """Tests for _clean_jira_url() smart-link artifact stripping."""

    def test_plain_url_unchanged(self):
        from resolve_source import _clean_jira_url

        url = "https://github.com/org/repo/pull/42"
        assert _clean_jira_url(url) == url

    def test_strips_smartlink_suffix(self):
        from resolve_source import _clean_jira_url

        raw = "https://github.com/org/repo/pull/42|smart-link]"
        assert _clean_jira_url(raw) == "https://github.com/org/repo/pull/42"

    def test_strips_brackets_and_smartlink(self):
        from resolve_source import _clean_jira_url

        raw = "[https://github.com/org/repo|smart-link]"
        assert _clean_jira_url(raw) == "https://github.com/org/repo"

    def test_strips_trailing_punctuation(self):
        from resolve_source import _clean_jira_url

        assert _clean_jira_url("https://github.com/org/repo.") == "https://github.com/org/repo"
        assert _clean_jira_url("https://github.com/org/repo),") == "https://github.com/org/repo"

    def test_strips_surrounding_parens(self):
        from resolve_source import _clean_jira_url

        raw = "(https://github.com/org/repo/pull/5)"
        assert _clean_jira_url(raw) == "https://github.com/org/repo/pull/5"


class TestExtractUrlsFromText:
    """Tests for _extract_urls_from_text() description parsing."""

    def test_single_pr_url(self):
        from resolve_source import _extract_urls_from_text

        text = "See the fix at https://github.com/org/repo/pull/42 for details."
        urls = _extract_urls_from_text(text)
        assert urls == ["https://github.com/org/repo/pull/42"]

    def test_multiple_urls_deduped(self):
        from resolve_source import _extract_urls_from_text

        text = (
            "PR: https://github.com/org/repo/pull/1\n"
            "Also: https://github.com/org/repo/pull/1\n"
            "And: https://github.com/other/lib/pull/7"
        )
        urls = _extract_urls_from_text(text)
        assert "https://github.com/org/repo/pull/1" in urls
        assert "https://github.com/other/lib/pull/7" in urls
        assert len(urls) == 2

    def test_smartlink_formatted_urls(self):
        from resolve_source import _extract_urls_from_text

        text = "Link: https://github.com/org/repo/pull/42|smart-link] end"
        urls = _extract_urls_from_text(text)
        assert urls == ["https://github.com/org/repo/pull/42"]

    def test_bare_repo_url(self):
        from resolve_source import _extract_urls_from_text

        text = "Source code: https://github.com/redhat-ai/agentic-starter-kits"
        urls = _extract_urls_from_text(text)
        assert urls == ["https://github.com/redhat-ai/agentic-starter-kits"]

    def test_gitlab_mr_url(self):
        from resolve_source import _extract_urls_from_text

        text = "MR: https://gitlab.cee.redhat.com/group/proj/-/merge_requests/99"
        urls = _extract_urls_from_text(text)
        assert urls == ["https://gitlab.cee.redhat.com/group/proj/-/merge_requests/99"]

    def test_empty_text_returns_empty(self):
        from resolve_source import _extract_urls_from_text

        assert _extract_urls_from_text("") == []
        assert _extract_urls_from_text(None) == []

    def test_non_git_urls_excluded(self):
        from resolve_source import _extract_urls_from_text

        text = "Docs at https://docs.google.com/document/d/abc123 and https://example.com/foo"
        urls = _extract_urls_from_text(text)
        assert urls == []


class TestDiscoverFromJiraWeightedScoring:
    """Tests for weighted scoring in _discover_from_jira()."""

    def _mock_issue_response(self, git_links=None, description=""):
        """Build a fake jira_reader.py --issue JSON response."""
        return json.dumps(
            {
                "issue_key": "TEST-1",
                "git_links": git_links or [],
                "description": description,
            }
        )

    def _mock_graph_response(self, pull_requests=None):
        """Build a fake jira_reader.py --graph JSON response."""
        return json.dumps(
            {
                "ticket": "TEST-1",
                "auto_discovered_urls": {"pull_requests": pull_requests or []},
            }
        )

    def test_description_url_discovered_when_no_remote_links(self, tmp_path):
        """A PR in the description should be discovered when no remote links exist."""
        from resolve_source import _discover_from_jira

        issue_resp = self._mock_issue_response(
            description="Fix is at https://github.com/org/repo/pull/42"
        )
        graph_resp = self._mock_graph_response()

        jira_script = tmp_path / "skills" / "jira-reader" / "scripts" / "jira_reader.py"
        jira_script.parent.mkdir(parents=True)
        jira_script.touch()

        def run_side_effect(cmd, **kwargs):
            if "--issue" in cmd:
                return _make_git_result(stdout=issue_resp)
            if "--graph" in cmd:
                return _make_git_result(stdout=graph_resp)
            return _make_git_result(returncode=1)

        with (
            patch("subprocess.run", side_effect=run_side_effect),
            patch("resolve_source._resolve_discovered_repos") as mock_resolve,
        ):
            mock_resolve.return_value = {"status": "resolved", "repo_path": "/resolved/repo"}
            _discover_from_jira("TEST-1", tmp_path / "workspace", tmp_path)

        mock_resolve.assert_called_once()
        discovered_arg = mock_resolve.call_args[0][0]
        assert len(discovered_arg) == 1
        assert discovered_arg[0]["repo_url"] == "https://github.com/org/repo"
        assert discovered_arg[0]["pr_urls"] == ["https://github.com/org/repo/pull/42"]

    def test_remote_link_ranked_first_over_description_url(self, tmp_path):
        """A remote-linked repo (weight 2) should be primary over a description-only repo."""
        from resolve_source import _discover_from_jira

        issue_resp = self._mock_issue_response(
            git_links=["https://github.com/org/main-repo/pull/10"],
            description="Also see https://github.com/org/other-repo/pull/99",
        )
        graph_resp = self._mock_graph_response()

        jira_script = tmp_path / "skills" / "jira-reader" / "scripts" / "jira_reader.py"
        jira_script.parent.mkdir(parents=True)
        jira_script.touch()

        def run_side_effect(cmd, **kwargs):
            if "--issue" in cmd:
                return _make_git_result(stdout=issue_resp)
            if "--graph" in cmd:
                return _make_git_result(stdout=graph_resp)
            return _make_git_result(returncode=1)

        with (
            patch("subprocess.run", side_effect=run_side_effect),
            patch("resolve_source._resolve_discovered_repos") as mock_resolve,
        ):
            mock_resolve.return_value = {"status": "resolved", "repo_path": "/resolved/repo"}
            _discover_from_jira("TEST-1", tmp_path / "workspace", tmp_path)

        mock_resolve.assert_called_once()
        discovered_arg = mock_resolve.call_args[0][0]
        assert len(discovered_arg) == 2
        assert discovered_arg[0]["repo_url"] == "https://github.com/org/main-repo"
        assert discovered_arg[1]["repo_url"] == "https://github.com/org/other-repo"

    def test_two_description_repos_resolves_both(self, tmp_path):
        """Two repos mentioned equally in description should resolve both (first = primary)."""
        from resolve_source import _discover_from_jira

        issue_resp = self._mock_issue_response(
            description=(
                "Repo A: https://github.com/org/repo-a\nRepo B: https://github.com/org/repo-b"
            ),
        )
        graph_resp = self._mock_graph_response()

        jira_script = tmp_path / "skills" / "jira-reader" / "scripts" / "jira_reader.py"
        jira_script.parent.mkdir(parents=True)
        jira_script.touch()

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        def run_side_effect(cmd, **kwargs):
            if "--issue" in cmd:
                return _make_git_result(stdout=issue_resp)
            if "--graph" in cmd:
                return _make_git_result(stdout=graph_resp)
            return _make_git_result(returncode=1)

        with (
            patch("subprocess.run", side_effect=run_side_effect),
            patch("resolve_source._clone_repo", return_value=True),
        ):
            result = _discover_from_jira("TEST-1", workspace, tmp_path)

        assert result["status"] == "resolved"
        assert "additional_repos" in result

    def test_description_url_not_double_counted_with_remote_link(self, tmp_path):
        """A URL present in both remote links and description should not get extra weight."""
        from resolve_source import _discover_from_jira

        pr_url = "https://github.com/org/repo/pull/42"
        issue_resp = self._mock_issue_response(
            git_links=[pr_url],
            description=f"The PR is {pr_url}",
        )
        graph_resp = self._mock_graph_response()

        jira_script = tmp_path / "skills" / "jira-reader" / "scripts" / "jira_reader.py"
        jira_script.parent.mkdir(parents=True)
        jira_script.touch()

        def run_side_effect(cmd, **kwargs):
            if "--issue" in cmd:
                return _make_git_result(stdout=issue_resp)
            if "--graph" in cmd:
                return _make_git_result(stdout=graph_resp)
            return _make_git_result(returncode=1)

        with (
            patch("subprocess.run", side_effect=run_side_effect),
            patch("resolve_source._resolve_discovered_repos") as mock_resolve,
        ):
            mock_resolve.return_value = {"status": "resolved", "repo_path": "/resolved/repo"}
            result = _discover_from_jira("TEST-1", tmp_path / "workspace", tmp_path)

        assert result["status"] == "resolved"
        mock_resolve.assert_called_once()
        discovered_arg = mock_resolve.call_args[0][0]
        assert len(discovered_arg) == 1
        assert discovered_arg[0]["pr_urls"] == [pr_url]
