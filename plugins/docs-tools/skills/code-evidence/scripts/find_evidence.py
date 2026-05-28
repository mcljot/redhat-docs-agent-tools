#!/usr/bin/env python3
"""Retrieve code evidence from a repository using hybrid search.

Wraps code-finder's Python API (claude_context.skills.evidence_retrieval).
Requires the code-finder package to be installed (`python3 -m pip install
code-finder`) or invoked via `uv run --with code-finder`.

Single query:
    python3 find_evidence.py --repo /path/to/repo --query "search query" \
        [--limit 5] [--filter-paths src/auth,src/config] [--reindex]

Batch mode (one import, one index load, many queries):
    python3 find_evidence.py --repo /path/to/repo \
        --queries-file queries.json [--reindex]

Secondary repos (targeted search with priority weighting):
    python3 find_evidence.py --repo /path/to/primary \
        --queries-file queries.json \
        --secondary-repos-file secondary-repos.json \
        [--secondary-weight 0.8]

queries.json schema:
    [
      {"query": "auth middleware", "limit": 5, "filter_paths": ["src/auth"]},
      {"query": "README overview",  "limit": 3}
    ]

secondary-repos.json schema:
    [
      {
        "repo_path": "/path/to/secondary-repo",
        "requirement_ids": ["REQ-002", "REQ-004"],
        "scope": {"include": ["pkg/controller/"], "exclude": null},
        "weight": 0.8
      }
    ]
"""

import argparse
import json
import sys
from pathlib import Path


def _parse_filter_paths(raw):
    """Parse comma-separated filter paths string into a list."""
    if not raw:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


def _resolve_filter_paths(repo_path, filter_paths):
    """Resolve filter paths relative to repo root to match index entries."""
    if not filter_paths:
        return None
    repo_root = Path(repo_path).resolve()
    return [str((repo_root / p).resolve()) for p in filter_paths]


def _format_result(
    query,
    filter_paths,
    repo_path,
    index_info,
    results,
    repo_priority="primary",
    weight=1.0,
):
    """Format searcher results into the evidence retrieval output dict."""
    return {
        "query": query,
        "repo_path": repo_path,
        "repo_priority": repo_priority,
        "result_count": len(results),
        "index_info": index_info,
        "results": [
            {
                "rank": i + 1,
                "file_path": r.file_path,
                "file_name": r.file_name,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "language": r.language,
                "chunk_type": r.chunk_type,
                "chunk_name": r.chunk_name,
                "parent_context": r.parent_context,
                "signature": r.signature,
                "docstring": r.docstring,
                "return_type": r.return_type,
                "content": r.content,
                "scores": {
                    "vector": round(r.vector_score, 4),
                    "bm25": round(r.bm25_score, 4),
                    "combined": round(r.combined_score, 4),
                    "adjusted": round(r.combined_score * weight, 4),
                },
                "repo_priority": repo_priority,
            }
            for i, r in enumerate(results)
        ],
    }


def _run_single(retrieve_evidence, repo, query, limit, filter_paths, reindex):
    """Run a single evidence retrieval and return the result dict."""
    return retrieve_evidence(
        repo_path=repo,
        query=query,
        limit=limit,
        filter_paths=filter_paths,
        reindex=reindex,
    )


def main():
    parser = argparse.ArgumentParser(description="Retrieve code evidence from a repository")
    parser.add_argument(
        "--repo",
        required=True,
        nargs="+",
        help="Path(s) to source code repository/repositories",
    )
    parser.add_argument("--query", help="Natural language search query (single mode)")
    parser.add_argument(
        "--queries-file",
        help="Path to JSON file with batch queries (see docstring for schema)",
    )
    parser.add_argument("--limit", type=int, default=5, help="Max results per query (default: 5)")
    parser.add_argument(
        "--filter-paths",
        help="Comma-separated directory prefixes to scope search (single mode)",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Force re-indexing (applied to first query only in batch mode)",
    )
    parser.add_argument(
        "--secondary-repos-file",
        help="JSON file specifying secondary repos with per-repo metadata",
    )
    parser.add_argument(
        "--secondary-weight",
        type=float,
        default=0.8,
        help="Relevance multiplier for secondary repo results (default: 0.8)",
    )
    args = parser.parse_args()

    if not args.query and not args.queries_file:
        parser.error("Either --query or --queries-file is required")
    if args.query and args.queries_file:
        parser.error("Use --query or --queries-file, not both")

    # In batch mode, validate the queries file before importing code-finder
    queries = None
    if args.queries_file:
        try:
            with open(args.queries_file) as f:
                queries = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading queries file: {e}", file=sys.stderr)
            sys.exit(1)

        if not isinstance(queries, list) or not queries:
            print("Error: queries file must contain a non-empty JSON array", file=sys.stderr)
            sys.exit(1)

        for i, entry in enumerate(queries):
            if not isinstance(entry, dict) or "query" not in entry:
                print(f"Error: entry {i} must be an object with a 'query' field", file=sys.stderr)
                sys.exit(1)

    secondary_repos = None
    if args.secondary_repos_file:
        try:
            with open(args.secondary_repos_file) as f:
                secondary_repos = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading secondary repos file: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(secondary_repos, list):
            print("Error: secondary repos file must contain a JSON array", file=sys.stderr)
            sys.exit(1)

    try:
        from claude_context.skills._index_manager import ensure_index
        from claude_context.skills.evidence_retrieval import retrieve_evidence
    except ImportError:
        print(
            "Error: code-finder is not installed. Run this script via:\n"
            "  uv run --with code-finder python3 find_evidence.py ...\n"
            "Or install code-finder directly: python3 -m pip install code-finder",
            file=sys.stderr,
        )
        sys.exit(1)

    reindex = args.reindex

    # Single query mode — use retrieve_evidence directly (one-shot, no reuse needed)
    if args.query:
        filter_paths = _parse_filter_paths(args.filter_paths)
        all_results = []
        for repo in args.repo:
            result = _run_single(
                retrieve_evidence,
                repo,
                args.query,
                args.limit,
                filter_paths,
                reindex,
            )
            all_results.append({"repo": repo, "result": result})
            reindex = False
        json.dump(all_results, sys.stdout, indent=2, default=str)
        print()
        return

    # Batch mode — call ensure_index once per repo, reuse searcher for all queries
    results = []
    for repo in args.repo:
        repo_path = str(Path(repo).resolve())
        searcher, index_info = ensure_index(repo_path, reindex=reindex)
        reindex = False
        for entry in queries:
            query = entry["query"]
            limit = entry.get("limit", args.limit)
            filter_paths = entry.get("filter_paths")
            resolved = _resolve_filter_paths(repo_path, filter_paths)

            raw = searcher.search(query=query, limit=limit, filter_paths=resolved)
            result = _format_result(query, filter_paths, repo_path, index_info, raw)
            results.append(
                {"repo": repo, "query": query, "filter_paths": filter_paths, "result": result}
            )

    # Secondary repos — index each independently, run subset of queries
    if secondary_repos and queries:
        for sec in secondary_repos:
            sec_path = str(Path(sec["repo_path"]).resolve())
            sec_weight = sec.get("weight", args.secondary_weight)
            sec_scope = sec.get("scope") or {}
            sec_include = sec_scope.get("include")

            sec_searcher, sec_index_info = ensure_index(sec_path, reindex=False)

            for entry in queries:
                query = entry["query"]
                limit = entry.get("limit", args.limit)
                filter_paths = sec_include if sec_include else entry.get("filter_paths")
                resolved = _resolve_filter_paths(sec_path, filter_paths)

                raw = sec_searcher.search(query=query, limit=limit, filter_paths=resolved)
                result = _format_result(
                    query,
                    filter_paths,
                    sec_path,
                    sec_index_info,
                    raw,
                    repo_priority="secondary",
                    weight=sec_weight,
                )
                results.append(
                    {
                        "repo": sec["repo_path"],
                        "query": query,
                        "filter_paths": filter_paths,
                        "result": result,
                        "repo_priority": "secondary",
                        "requirement_ids": sec.get("requirement_ids", []),
                    }
                )

    json.dump(results, sys.stdout, indent=2, default=str)
    print()


if __name__ == "__main__":
    main()
