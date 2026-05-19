"""Tests for synchronizing resolved source info into workflow progress files."""

import json


def _write_progress(progress_file, base_path, steps):
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    progress = {
        "workflow_type": "docs-workflow-code-evidence",
        "ticket": "PROJ-123",
        "base_path": str(base_path),
        "status": "in_progress",
        "created_at": "2026-05-19T09:00:00Z",
        "updated_at": "2026-05-19T09:00:00Z",
        "options": {
            "format": "adoc",
            "draft": False,
            "create_merge_request": False,
            "pr_urls": [],
            "source": None,
            "additional_sources": [],
        },
        "step_order": ["requirements", "scope-req-audit", "planning", "code-evidence"],
        "steps": steps,
    }
    progress_file.write_text(json.dumps(progress, indent=2) + "\n")


def test_sync_progress_source_rehydrates_from_source_yaml(tmp_path):
    """A cached source.yaml should repopulate options.source on resume."""
    from sync_progress_source import sync_progress_source

    base_path = tmp_path / "proj-123"
    base_path.mkdir()
    repo_dir = tmp_path / "agentic-starter-kits"
    repo_dir.mkdir()
    (base_path / "source.yaml").write_text(f"repo: {repo_dir}\n")

    progress_file = base_path / "workflow" / "docs-workflow-code-evidence_proj-123.json"
    _write_progress(
        progress_file,
        base_path,
        {
            "requirements": {"status": "completed", "output": "requirements", "result": None},
            "scope-req-audit": {"status": "deferred", "output": None, "result": None},
            "planning": {"status": "pending", "output": None, "result": None},
            "code-evidence": {"status": "deferred", "output": None, "result": None},
        },
    )

    result = sync_progress_source(
        base_path=base_path,
        progress_file=progress_file,
    )

    assert result["status"] == "resolved"

    updated = json.loads(progress_file.read_text())
    assert updated["options"]["source"]["repo_path"] == str(repo_dir)
    assert updated["options"]["additional_sources"] == []
    assert updated["steps"]["scope-req-audit"]["status"] == "pending"
    assert updated["steps"]["planning"]["status"] == "pending"
    assert updated["steps"]["code-evidence"]["status"] == "pending"
    assert updated["updated_at"] != "2026-05-19T09:00:00Z"


def test_sync_progress_source_can_skip_deferred_steps_when_still_unresolved(tmp_path):
    """Post-requirements sync should skip deferred steps when no source exists."""
    from sync_progress_source import sync_progress_source

    base_path = tmp_path / "proj-456"
    base_path.mkdir()
    progress_file = base_path / "workflow" / "docs-workflow-code-evidence_proj-456.json"
    _write_progress(
        progress_file,
        base_path,
        {
            "requirements": {"status": "completed", "output": "requirements", "result": None},
            "scope-req-audit": {"status": "deferred", "output": None, "result": None},
            "planning": {"status": "pending", "output": None, "result": None},
            "code-evidence": {"status": "deferred", "output": None, "result": None},
        },
    )

    result = sync_progress_source(
        base_path=base_path,
        progress_file=progress_file,
        skip_deferred_on_no_source=True,
    )

    assert result["status"] == "no_source"

    updated = json.loads(progress_file.read_text())
    assert updated["steps"]["scope-req-audit"]["status"] == "skipped"
    assert updated["steps"]["planning"]["status"] == "pending"
    assert updated["steps"]["code-evidence"]["status"] == "skipped"
