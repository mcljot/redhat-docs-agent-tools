#!/usr/bin/env python3
"""Synchronize resolved source info into a workflow progress file.

This script bridges deterministic repo resolution (`resolve_source.py`) and the
workflow progress state used by the docs orchestrator. It is intended for:

1. Resume-time rehydration of `options.source` from `source.yaml`
2. Post-requirements source resolution that should also update deferred steps
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from resolve_source import resolve


def _utc_now_iso():
    """Return a compact UTC timestamp suitable for progress files."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _set_deferred_steps(progress, new_status):
    """Update all deferred steps to the provided status."""
    for step_data in progress.get("steps", {}).values():
        if step_data.get("status") == "deferred":
            step_data["status"] = new_status


def _load_progress(progress_file):
    """Load a workflow progress file."""
    with open(progress_file) as f:
        return json.load(f)


def _write_progress(progress_file, progress):
    """Write the updated progress file back to disk."""
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)
        f.write("\n")


def sync_progress_source(
    base_path,
    progress_file,
    ticket=None,
    plugin_root=None,
    repo_values=None,
    pr_urls=None,
    scan_requirements=False,
    skip_deferred_on_no_source=False,
):
    """Resolve source info and write it into the progress file.

    Args:
        base_path: Workflow base path (e.g. .agent_workspace/proj-123)
        progress_file: Path to the workflow progress JSON file
        ticket: Optional JIRA ticket key for JIRA-based discovery
        plugin_root: Optional docs-tools plugin root for locating jira_reader.py
        repo_values: Optional explicit repo value(s) to pass through
        pr_urls: Optional explicit PR/MR URLs to pass through
        scan_requirements: Whether to enable requirements.md fallback scanning
        skip_deferred_on_no_source: If True, unresolved source changes deferred
            steps to skipped (used after requirements completes)

    Returns:
        Result dict from `resolve_source.resolve()`, plus `progress_updated`.
    """
    base_path = Path(base_path)
    progress_file = Path(progress_file)
    progress = _load_progress(progress_file)

    options = progress.setdefault("options", {})
    resolved_prs = pr_urls if pr_urls is not None else options.get("pr_urls") or None

    args = SimpleNamespace(
        base_path=str(base_path),
        repo=repo_values,
        pr=resolved_prs,
        ticket=ticket,
        plugin_root=plugin_root,
        scan_requirements=scan_requirements,
        dry_run=False,
    )
    result = resolve(args)

    progress_updated = False

    if result["status"] == "resolved":
        options["source"] = {
            "repo_path": result["repo_path"],
            "repo_url": result.get("repo_url"),
            "ref": result.get("ref"),
            "scope": result.get("scope"),
        }
        options["additional_sources"] = result.get("additional_repos", [])
        _set_deferred_steps(progress, "pending")
        progress_updated = True
    elif result["status"] == "no_source" and skip_deferred_on_no_source:
        _set_deferred_steps(progress, "skipped")
        progress_updated = True

    if progress_updated:
        progress["updated_at"] = _utc_now_iso()
        _write_progress(progress_file, progress)

    result["progress_updated"] = progress_updated
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Resolve source state and sync it into a workflow progress file"
    )
    parser.add_argument(
        "--base-path",
        required=True,
        help="Workflow base path (e.g. .agent_workspace/proj-123)",
    )
    parser.add_argument(
        "--progress-file",
        required=True,
        help="Workflow progress JSON file to update",
    )
    parser.add_argument(
        "--ticket",
        help="Optional JIRA ticket key for JIRA-based source discovery",
    )
    parser.add_argument(
        "--plugin-root",
        help="Optional docs-tools plugin root for locating jira_reader.py",
    )
    parser.add_argument(
        "--repo",
        nargs="+",
        help="Optional explicit source repo value(s) to pass through",
    )
    parser.add_argument(
        "--pr",
        nargs="+",
        help="Optional explicit PR/MR URLs to pass through",
    )
    parser.add_argument(
        "--scan-requirements",
        action="store_true",
        help="Enable requirements.md fallback scanning",
    )
    parser.add_argument(
        "--skip-deferred-on-no-source",
        action="store_true",
        help="Mark deferred steps skipped when no source is found",
    )
    args = parser.parse_args()

    try:
        result = sync_progress_source(
            base_path=args.base_path,
            progress_file=args.progress_file,
            ticket=args.ticket,
            plugin_root=args.plugin_root,
            repo_values=args.repo,
            pr_urls=args.pr,
            scan_requirements=args.scan_requirements,
            skip_deferred_on_no_source=args.skip_deferred_on_no_source,
        )
    except (OSError, json.JSONDecodeError) as e:
        json.dump({"status": "error", "message": str(e)}, sys.stdout, indent=2)
        print()
        sys.exit(1)

    json.dump(result, sys.stdout, indent=2)
    print()

    if result["status"] in ("error", "clone_failed"):
        sys.exit(1)
    if result["status"] == "no_source":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
