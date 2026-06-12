"""Watch MR/PR for new SME review comments.

Polls an MR/PR for review comments created after a given timestamp.
Maintains a last-checked timestamp for incremental polling.

Usage:
    python3 watch_mr.py --mr-url <url> --base-path <path> [--since <ISO8601>]
    python3 watch_mr.py --base-path <path>  # reads URL from step-result.json
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def find_mr_url(base_path):
    """Read MR URL from create-merge-request/step-result.json."""
    sidecar = Path(base_path) / "create-merge-request" / "step-result.json"
    if not sidecar.exists():
        return None, None
    data = json.loads(sidecar.read_text())
    if data.get("skipped"):
        return None, None
    return data.get("url"), data.get("completed_at")


def find_git_pr_reader():
    """Locate the git_pr_reader.py script."""
    candidates = [
        Path(os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
        / "skills" / "git-pr-reader" / "scripts" / "git_pr_reader.py",
        Path(__file__).resolve().parents[3]
        / "git-pr-reader" / "scripts" / "git_pr_reader.py",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "git_pr_reader.py"


def fetch_comments(mr_url, reader_script):
    """Fetch comments from MR/PR via git_pr_reader.py."""
    result = subprocess.run(
        ["python3", reader_script, "comments", mr_url, "--json"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        print(f"WARNING: git_pr_reader failed: {result.stderr[:200]}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"WARNING: Could not parse comments JSON", file=sys.stderr)
        return []


def parse_timestamp(ts_str):
    """Parse ISO 8601 timestamp string to datetime."""
    if not ts_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    ts_str = ts_str.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=timezone.utc)


def load_last_checked(base_path):
    """Load last-checked state from disk."""
    state_file = Path(base_path) / "watch-mr" / "last-checked.json"
    if not state_file.exists():
        return None, set()
    data = json.loads(state_file.read_text())
    return data.get("last_checked"), set(data.get("comments_seen", []))


def save_last_checked(base_path, timestamp, seen_ids):
    """Save last-checked state to disk."""
    state_dir = Path(base_path) / "watch-mr"
    state_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "last_checked": timestamp,
        "comments_seen": sorted(seen_ids),
    }
    (state_dir / "last-checked.json").write_text(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Watch MR for new comments")
    parser.add_argument("--mr-url", default=None)
    parser.add_argument("--base-path", required=True)
    parser.add_argument("--since", default=None, help="ISO 8601 timestamp baseline")
    args = parser.parse_args()

    base_path = Path(args.base_path)

    mr_url = args.mr_url
    mr_created = None
    if not mr_url:
        mr_url, mr_created = find_mr_url(base_path)

    if not mr_url:
        result = {"new_comments": [], "count": 0, "action_needed": False,
                  "error": "No MR URL found"}
        json.dump(result, sys.stdout, indent=2)
        print()
        sys.exit(0)

    last_checked_str, seen_ids = load_last_checked(base_path)
    since_str = args.since or last_checked_str or mr_created
    since_dt = parse_timestamp(since_str)

    reader_script = find_git_pr_reader()
    all_comments = fetch_comments(mr_url, reader_script)

    new_comments = []
    all_seen = set(seen_ids)
    for c in all_comments:
        cid = str(c.get("id", ""))
        if c.get("resolved", False):
            continue
        created = parse_timestamp(c.get("created_at", ""))
        if created > since_dt and cid not in seen_ids:
            new_comments.append(c)
            all_seen.add(cid)

    now = datetime.now(timezone.utc).isoformat()
    save_last_checked(base_path, now, all_seen)

    result = {
        "new_comments": new_comments,
        "count": len(new_comments),
        "action_needed": len(new_comments) > 0,
        "mr_url": mr_url,
        "checked_at": now,
        "since": since_str,
    }
    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
