"""Tests for find_evidence.py — secondary repos and repo_priority metadata."""

from types import SimpleNamespace

from find_evidence import _format_result, _resolve_filter_paths


class TestFormatResult:
    def _make_result(self, combined=0.75, vector=0.3, bm25=12.0):
        return SimpleNamespace(
            file_path="pkg/controller/reconciler.go",
            file_name="reconciler.go",
            start_line=10,
            end_line=50,
            language="go",
            chunk_type="function",
            chunk_name="Reconcile",
            parent_context="ReconcilerImpl",
            signature="func (r *ReconcilerImpl) Reconcile(ctx context.Context)",
            docstring="Reconcile handles the reconciliation loop.",
            return_type="error",
            content="func (r *ReconcilerImpl) Reconcile(...) { ... }",
            vector_score=vector,
            bm25_score=bm25,
            combined_score=combined,
        )

    def test_primary_defaults(self):
        r = self._make_result()
        out = _format_result("test query", None, "/repo", {}, [r])
        assert out["repo_priority"] == "primary"
        assert out["results"][0]["repo_priority"] == "primary"
        assert out["results"][0]["scores"]["adjusted"] == 0.75

    def test_secondary_with_weight(self):
        r = self._make_result(combined=0.80)
        out = _format_result(
            "test query",
            None,
            "/repo",
            {},
            [r],
            repo_priority="secondary",
            weight=0.8,
        )
        assert out["repo_priority"] == "secondary"
        assert out["results"][0]["repo_priority"] == "secondary"
        assert out["results"][0]["scores"]["adjusted"] == 0.64
        assert out["results"][0]["scores"]["combined"] == 0.80

    def test_weight_one_preserves_score(self):
        r = self._make_result(combined=0.90)
        out = _format_result(
            "q",
            None,
            "/repo",
            {},
            [r],
            repo_priority="primary",
            weight=1.0,
        )
        assert out["results"][0]["scores"]["adjusted"] == 0.90

    def test_empty_results(self):
        out = _format_result("q", None, "/repo", {}, [])
        assert out["result_count"] == 0
        assert out["results"] == []
        assert out["repo_priority"] == "primary"


class TestResolveFilterPaths:
    def test_none_input(self):
        assert _resolve_filter_paths("/repo", None) is None

    def test_resolves_relative(self, tmp_path):
        repo = tmp_path / "myrepo"
        repo.mkdir()
        result = _resolve_filter_paths(str(repo), ["pkg/api"])
        assert len(result) == 1
        assert result[0].endswith("pkg/api")
