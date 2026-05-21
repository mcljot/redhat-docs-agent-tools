#!/usr/bin/env python3
"""Extract public API surface from source files using AST parsing.

Wraps code-finder's Python API (claude_context.skills.api_surface).
Requires the code-finder package to be installed (`python3 -m pip install
code-finder`) or invoked via `uv run --with code-finder`.

Usage:
    python3 api_surface.py --target /path/to/source \
        [--languages python,go] [--include-private] [--no-docstrings]
        [--summary]
"""

import argparse
import json
import sys
from collections import Counter


def _summarize(result):
    """Print a human-readable summary of the API surface to stdout."""
    surface = result.get("api_surface", {})
    type_counts = Counter()
    names_by_type = {}

    for file_info in surface.values():
        for entity in file_info.get("entities", []):
            etype = entity.get("type", "unknown")
            type_counts[etype] += 1
            names_by_type.setdefault(etype, []).append(entity.get("name", "?"))

    lines = [
        f"Files processed: {result.get('files_processed', 0)}",
        f"Files with API entities: {result.get('files_with_api', 0)}",
        f"Total entities: {result.get('total_entities', 0)}",
    ]
    if type_counts:
        breakdown = ", ".join(f"{t}={c}" for t, c in type_counts.most_common())
        lines.append(f"By type: {breakdown}")
        for etype, names in sorted(names_by_type.items()):
            preview = names[:10]
            suffix = f" (+{len(names) - 10} more)" if len(names) > 10 else ""
            lines.append(f"  {etype}: {', '.join(preview)}{suffix}")

    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Extract public API surface from source files")
    parser.add_argument(
        "--target",
        required=True,
        help="Path to a file or directory to analyze",
    )
    parser.add_argument(
        "--languages",
        help="Comma-separated language filter (e.g., python,typescript)",
    )
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Include private names (prefixed with _)",
    )
    parser.add_argument(
        "--no-docstrings",
        action="store_true",
        help="Exclude docstrings from output",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a human-readable summary instead of full JSON",
    )
    args = parser.parse_args()

    languages = None
    if args.languages:
        languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]

    try:
        from claude_context.skills.api_surface import extract_api_surface
    except ImportError:
        print(
            "Error: code-finder is not installed. Run this script via:\n"
            "  uv run --with code-finder python3 api_surface.py ...\n"
            "Or install code-finder directly: python3 -m pip install code-finder",
            file=sys.stderr,
        )
        sys.exit(1)

    result = extract_api_surface(
        target_path=args.target,
        languages=languages,
        include_private=args.include_private,
        include_docstrings=not args.no_docstrings,
    )

    if args.summary:
        _summarize(result)
    else:
        json.dump(result, sys.stdout, indent=2, default=str)
        print()


if __name__ == "__main__":
    main()
