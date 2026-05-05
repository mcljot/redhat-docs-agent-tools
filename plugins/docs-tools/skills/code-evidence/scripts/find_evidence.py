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

queries.json schema:
    [
      {"query": "auth middleware", "limit": 5, "filter_paths": ["src/auth"]},
      {"query": "README overview",  "limit": 3}
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


def _format_result(query, filter_paths, repo_path, index_info, results):
    """Format searcher results into the evidence retrieval output dict."""
    return {
        "query": query,
        "repo_path": repo_path,
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
                },
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
    parser.add_argument("--repo", required=True, help="Path to the repository")
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

    # Single query mode — use retrieve_evidence directly (one-shot, no reuse needed)
    if args.query:
        filter_paths = _parse_filter_paths(args.filter_paths)
        result = _run_single(
            retrieve_evidence,
            args.repo,
            args.query,
            args.limit,
            filter_paths,
            args.reindex,
        )
        json.dump(result, sys.stdout, indent=2, default=str)
        print()
        return

    # Batch mode — call ensure_index once, reuse searcher for all queries
    searcher, index_info = ensure_index(args.repo, reindex=args.reindex)
    repo_path = str(Path(args.repo).resolve())

    results = []
    for entry in queries:
        query = entry["query"]
        limit = entry.get("limit", args.limit)
        filter_paths = entry.get("filter_paths")
        resolved = _resolve_filter_paths(repo_path, filter_paths)

        raw = searcher.search(query=query, limit=limit, filter_paths=resolved)
        result = _format_result(query, filter_paths, repo_path, index_info, raw)
        results.append({"query": query, "filter_paths": filter_paths, "result": result})

    json.dump(results, sys.stdout, indent=2, default=str)
    print()


if __name__ == "__main__":
    main()
