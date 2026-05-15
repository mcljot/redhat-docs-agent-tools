#!/usr/bin/env python3
"""Extract repo/PR URLs from JIRA ticket graph data.

Reads JSON ticket data on stdin (from jira_reader.py --graph or similar),
extracts all repo and PR URLs from git_links and auto_discovered_urls,
groups by normalized repo URL, and writes discovered_repos.json.

Usage:
    python3 jira_reader.py --graph PROJ-123 | \
        python3 extract_discovered_repos.py \
        --output-dir .agent_workspace/proj-123/requirements
    cat graph-data.json | python3 extract_discovered_repos.py --output-dir /path/to/output
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "docs-orchestrator" / "scripts"),
)
from resolve_source import extract_repo_url, normalize_git_url

GITHUB_PR_RE = re.compile(r"https?://github\.com/[^/]+/[^/]+/pull/\d+")
GITLAB_MR_RE = re.compile(r"https?://gitlab\.[^/]+/.+?/-/merge_requests/\d+")


def extract_repos_from_graph(graph_data):
    """Extract and group repo/PR URLs from JIRA graph data.

    Accepts either:
    - A single ticket's graph output (from jira_reader.py --graph): has
      "issue_key", "git_links", "auto_discovered_urls", "children", etc.
    - A dict of tickets keyed by ticket key (from jira_graph_walker.py):
      each value has "git_links", "auto_discovered_urls"

    Returns dict matching discovered_repos.json schema.
    """
    tickets = {}

    if "issue_key" in graph_data:
        tickets[graph_data["issue_key"]] = graph_data
        for child in graph_data.get("children", {}).get("issues", []):
            key = child.get("key")
            if key:
                tickets[key] = child
        for link in graph_data.get("issue_links", {}).get("links", []):
            key = link.get("key")
            if key:
                tickets[key] = link
    elif "tickets" in graph_data:
        tickets = graph_data["tickets"]
    else:
        tickets = graph_data

    repo_groups = {}

    for ticket_key, ticket in tickets.items():
        all_urls = list(ticket.get("git_links", []))

        auto = ticket.get("auto_discovered_urls", {})
        for pr_url in auto.get("pull_requests", []):
            if pr_url not in all_urls:
                all_urls.append(pr_url)

        seen_urls = set()
        unique_urls = []
        for url in all_urls:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_urls.append(url)

        for url in unique_urls:
            repo_url = extract_repo_url(url)
            if not repo_url:
                continue

            normalized = normalize_git_url(repo_url)

            if normalized not in repo_groups:
                repo_groups[normalized] = {
                    "repo_url": repo_url,
                    "pr_urls": set(),
                    "source_tickets": set(),
                }

            repo_groups[normalized]["source_tickets"].add(ticket_key)

            if GITHUB_PR_RE.match(url) or GITLAB_MR_RE.match(url):
                repo_groups[normalized]["pr_urls"].add(url)

    repos = []
    total_prs = 0
    for _normalized, group in sorted(
        repo_groups.items(), key=lambda x: len(x[1]["source_tickets"]), reverse=True
    ):
        pr_list = sorted(group["pr_urls"])
        repos.append(
            {
                "repo_url": group["repo_url"],
                "normalized": _normalized,
                "reference_count": len(group["source_tickets"]),
                "pr_urls": pr_list,
                "source_tickets": sorted(group["source_tickets"]),
            }
        )
        total_prs += len(pr_list)

    return {
        "repos": repos,
        "total_repos": len(repos),
        "total_prs": total_prs,
    }


def main():
    parser = argparse.ArgumentParser(description="Extract repo/PR URLs from JIRA ticket graph data")
    parser.add_argument(
        "--output-dir", required=True, help="Directory to write discovered_repos.json"
    )
    args = parser.parse_args()

    try:
        graph_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)

    result = extract_repos_from_graph(graph_data)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "discovered_repos.json"

    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    print(
        f"Wrote {output_file}: {result['total_repos']} repos, {result['total_prs']} PRs",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
